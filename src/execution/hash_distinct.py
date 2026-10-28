"""Disk-backed hash duplicate elimination."""

import hashlib
import json
import tempfile
from collections.abc import Generator
from pathlib import Path

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.sort import Sort
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter
from src.execution.temp_run import tuple_size
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]


class _PartitionScan(Operator):
    """Adapt a temporary partition to the Sort operator."""

    def __init__(self, path: Path, schema: list[tuple[str, str]]):
        super().__init__()
        self.path = path
        self.schema = list(schema)
        self._reader: TempPageReader | None = None

    def open(self) -> None:
        self.close()
        self._counters.tuples_out = 0
        self._counters.page_reads = 0
        self._reader = TempPageReader(self.path)

    def next(self) -> Row | None:
        if self._reader is None:
            raise RuntimeError("Partition scan is not open")

        before = self._reader.page_reads
        row = self._reader.read()
        self._counters.page_reads += self._reader.page_reads - before

        if row is not None:
            self._counters.tuples_out += 1

        return row

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


class HashDistinct(Operator):
    """Hash-partition rows and remove duplicates with bounded memory."""

    def __init__(self, child: Operator, pages: SharedPageManager):
        super().__init__()
        self.child = child
        self.pages = pages
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._partitions: list[Path] = []
        self._iterator: Generator[Row, None, None] | None = None
        self._opened = False

    @staticmethod
    def _partition_index(row: Row, count: int) -> int:
        encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        digest = hashlib.blake2b(encoded, digest_size=8).digest()
        return int.from_bytes(digest, "big") % count

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0

        try:
            self.child.open()
            self.schema = list(self.child.schema)

            self._directory = tempfile.TemporaryDirectory(
                prefix="execution_hash_distinct_"
            )
            root = Path(self._directory.name)

            count = self.pages.capacity - 1
            self._partitions = [
                root / f"partition_{index}.tmp" for index in range(count)
            ]

            # Reserve B-1 output frames; leave one for the scan.
            with self.pages.temporary_frames(count) as buffers:
                writers = [
                    TempPageWriter(path, buffer)
                    for path, buffer in zip(self._partitions, buffers, strict=True)
                ]

                try:
                    while (row := self.child.next()) is not None:
                        index = self._partition_index(row, count)
                        writers[index].write(row)
                finally:
                    for writer in writers:
                        writer.close()
                        self._counters.page_writes += writer.page_writes

            self.child.close()
            self._iterator = self._emit_partitions()
            self._opened = True

        except Exception:
            self.close()
            raise

    def _emit_partitions(self) -> Generator[Row, None, None]:
        # One frame for input and at most B-2 pages of hash entries.
        memory_limit = (self.pages.capacity - 2) * PAGE_SIZE

        for path in self._partitions:
            seen: dict[Row, None] = {}
            used_bytes = 0
            overflow = False

            with (
                self.pages.temporary_frames(1) as buffers,
                TempPageReader(path, buffers[0]) as reader,
            ):
                while (row := reader.read()) is not None:
                    self._counters.comparisons += 1

                    if row in seen:
                        continue

                    size = tuple_size(row)

                    if used_bytes + size > memory_limit:
                        overflow = True
                        break

                    seen[row] = None
                    used_bytes += size

                self._counters.page_reads += reader.page_reads

            if not overflow:
                yield from seen
                continue

            # A skewed or oversized partition must not grow its
            # hash table beyond the memory budget. Use external sort.
            seen.clear()

            scan = _PartitionScan(path, self.schema)
            keys = [(name, "asc") for name, _ in self.schema]
            sorter = Sort(scan, keys, self.pages)

            try:
                sorter.open()
                previous: Row | None = None

                while (row := sorter.next()) is not None:
                    if previous is not None:
                        self._counters.comparisons += 1
                        if row == previous:
                            continue

                    previous = row
                    yield row
            finally:
                sort_counts = sorter.counters()
                scan_counts = scan.counters()

                self._counters.page_reads += (
                    sort_counts["page_reads"] + scan_counts["page_reads"]
                )
                self._counters.page_writes += sort_counts["page_writes"]
                sorter.close()

    def next(self) -> Row | None:
        if not self._opened or self._iterator is None:
            raise RuntimeError("HashDistinct is not open")

        row = next(self._iterator, None)

        if row is not None:
            self._counters.tuples_out += 1

        return row

    def close(self) -> None:
        if self._iterator is not None:
            self._iterator.close()
            self._iterator = None

        self.child.close()

        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

        self._partitions = []
        self._opened = False
