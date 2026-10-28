"""Grace hash equijoin with bounded hash tables and disk fallback."""

import hashlib
import json
import tempfile
from collections.abc import Generator
from pathlib import Path

from src.execution.column_resolver import resolve_column
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter
from src.execution.temp_run import tuple_size
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]


class GraceHashJoin(Operator):
    """Partition both inputs and join matching hash partitions."""

    def __init__(
        self,
        left: Operator,
        right: Operator,
        left_key: str,
        right_key: str,
        pages: SharedPageManager,
    ) -> None:
        super().__init__()
        self.left = left
        self.right = right
        self.left_key = left_key
        self.right_key = right_key
        self.pages = pages

        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._left_paths: list[Path] = []
        self._right_paths: list[Path] = []
        self._left_index = -1
        self._right_index = -1
        self._iterator: Generator[Row, None, None] | None = None
        self._opened = False
        # Actual partition statistics collected during execution.
        self.left_partition_rows: list[int] = []
        self.right_partition_rows: list[int] = []
        self.left_partition_pages: list[int] = []
        self.right_partition_pages: list[int] = []
        self.overflow_partition_count = 0

    @staticmethod
    def _column_index(
        schema: list[tuple[str, str]],
        column: str,
    ) -> int:
        return resolve_column(schema, column)

    @staticmethod
    def _partition_index(value: str | float, count: int) -> int:
        encoded = json.dumps(
            (value,),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.blake2b(encoded, digest_size=8).digest()
        return int.from_bytes(digest, "big") % count

    def _partition(
        self,
        child: Operator,
        paths: list[Path],
        key_index: int,
    ) -> None:
        count = len(paths)
        partition_rows = [0] * count

        # B-1 output buffers, leaving one frame available.
        with self.pages.temporary_frames(count) as buffers:
            writers = [
                TempPageWriter(path, buffer)
                for path, buffer in zip(paths, buffers, strict=True)
            ]

            try:
                while (row := child.next()) is not None:
                    index = self._partition_index(row[key_index], count)
                    writers[index].write(row)
                    partition_rows[index] += 1
            finally:
                for writer in writers:
                    writer.close()
                    self._counters.page_writes += writer.page_writes

            # Store the actual partition sizes and physical temporary-page counts.
            partition_pages = [path.stat().st_size // PAGE_SIZE for path in paths]

            if child is self.left:
                self.left_partition_rows = partition_rows
                self.left_partition_pages = partition_pages
            else:
                self.right_partition_rows = partition_rows
                self.right_partition_pages = partition_pages

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self.left_partition_rows = []
        self.right_partition_rows = []
        self.left_partition_pages = []
        self.right_partition_pages = []
        self.overflow_partition_count = 0

        try:
            self.left.open()
            self.right.open()

            self._left_index = self._column_index(self.left.schema, self.left_key)
            self._right_index = self._column_index(self.right.schema, self.right_key)
            self.schema = list(self.left.schema) + list(self.right.schema)

            self._directory = tempfile.TemporaryDirectory(
                prefix="execution_grace_hash_join_"
            )
            root = Path(self._directory.name)
            count = self.pages.capacity - 1

            self._left_paths = [root / f"left_{i}.tmp" for i in range(count)]
            self._right_paths = [root / f"right_{i}.tmp" for i in range(count)]

            self._partition(self.left, self._left_paths, self._left_index)
            self.left.close()

            self._partition(self.right, self._right_paths, self._right_index)
            self.right.close()

            self._iterator = self._join_partitions()
            self._opened = True

        except Exception:
            self.close()
            raise

    def _hash_join_partition(
        self,
        left_path: Path,
        right_path: Path,
    ) -> Generator[Row, None, None]:
        """Build a bounded left-side hash table, then probe right."""
        memory_limit = (self.pages.capacity - 2) * PAGE_SIZE
        table: dict[int | str | float, list[Row]] = {}
        used_bytes = 0
        overflow = False

        with self.pages.temporary_frames(1) as buffers:
            reader = TempPageReader(left_path, buffers[0])
            try:
                while (row := reader.read()) is not None:
                    size = tuple_size(row) + 64

                    if used_bytes + size > memory_limit:
                        overflow = True
                        break

                    key = row[self._left_index]
                    table.setdefault(key, []).append(row)
                    used_bytes += size
            finally:
                reader.close()
                self._counters.page_reads += reader.page_reads

        if overflow:
            self.overflow_partition_count += 1
            table.clear()
            yield from self._fallback(left_path, right_path)
            return

        with self.pages.temporary_frames(1) as buffers:
            reader = TempPageReader(right_path, buffers[0])
            try:
                while (right := reader.read()) is not None:
                    key = right[self._right_index]
                    matches = table.get(key, [])

                    self._counters.comparisons += 1

                    for left in matches:
                        yield left + right
            finally:
                reader.close()
                self._counters.page_reads += reader.page_reads

    def _fallback(
        self,
        left_path: Path,
        right_path: Path,
    ) -> Generator[Row, None, None]:
        """Join an oversized partition with bounded disk rescans."""
        with self.pages.temporary_frames(2) as buffers:
            left_reader = TempPageReader(left_path, buffers[0])

            try:
                while (left := left_reader.read()) is not None:
                    right_reader = TempPageReader(right_path, buffers[1])

                    try:
                        while (right := right_reader.read()) is not None:
                            self._counters.comparisons += 1

                            if left[self._left_index] == right[self._right_index]:
                                yield left + right
                    finally:
                        right_reader.close()
                        self._counters.page_reads += right_reader.page_reads
            finally:
                left_reader.close()
                self._counters.page_reads += left_reader.page_reads

    def _join_partitions(self) -> Generator[Row, None, None]:
        for left_path, right_path in zip(
            self._left_paths, self._right_paths, strict=True
        ):
            yield from self._hash_join_partition(left_path, right_path)

    def next(self) -> Row | None:
        if not self._opened or self._iterator is None:
            raise RuntimeError("GraceHashJoin is not open")

        row = next(self._iterator, None)

        if row is not None:
            self._counters.tuples_out += 1

        return row

    def close(self) -> None:
        if self._iterator is not None:
            self._iterator.close()
            self._iterator = None

        self.left.close()
        self.right.close()

        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

        self._left_paths = []
        self._right_paths = []
        self._opened = False
