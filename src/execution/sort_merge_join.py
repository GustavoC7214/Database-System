"""External sort-merge equijoin with duplicate-key support."""

import tempfile
from pathlib import Path

from src.execution.column_resolver import resolve_column
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.sort import Sort
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter

Row = tuple[int | str | float, ...]


class SortMergeJoin(Operator):
    """Sort both relations and merge matching equality keys."""

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
        self._left_reader: TempPageReader | None = None
        self._right_reader: TempPageReader | None = None
        self._group_reader: TempPageReader | None = None

        self._left_path: Path | None = None
        self._right_path: Path | None = None
        self._group_path: Path | None = None

        self._buffer_context = None
        self._buffers = None

        self._left_index = -1
        self._right_index = -1
        self._left_row: Row | None = None
        self._right_row: Row | None = None
        self._group_key: int | str | float | None = None
        self._group_left: Row | None = None
        self._opened = False

    @staticmethod
    def _column_index(
        schema: list[tuple[str, str]],
        column: str,
    ) -> int:
        return resolve_column(schema, column)

    def _materialize_sorted(
        self,
        child: Operator,
        key: str,
        path: Path,
    ) -> None:
        sorter = Sort(child, [(key, "ASC")], self.pages)

        try:
            sorter.open()

            with self.pages.temporary_frames(1) as buffers:
                writer = TempPageWriter(path, buffers[0])
                try:
                    while (row := sorter.next()) is not None:
                        writer.write(row)
                finally:
                    writer.close()
                    self._counters.page_writes += writer.page_writes
        finally:
            sorter.close()
            statistics = sorter.counters()
            self._counters.page_reads += statistics["page_reads"]
            self._counters.page_writes += statistics["page_writes"]

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0

        try:
            # Establish schemas before sorting.
            self.left.open()
            self.right.open()

            self._left_index = self._column_index(self.left.schema, self.left_key)
            self._right_index = self._column_index(self.right.schema, self.right_key)
            self.schema = list(self.left.schema) + list(self.right.schema)

            self.left.close()
            self.right.close()

            self._directory = tempfile.TemporaryDirectory(
                prefix="execution_sort_merge_join_"
            )
            root = Path(self._directory.name)
            self._left_path = root / "left.tmp"
            self._right_path = root / "right.tmp"
            self._group_path = root / "group.tmp"

            self._materialize_sorted(self.left, self.left_key, self._left_path)
            self._materialize_sorted(self.right, self.right_key, self._right_path)

            self._buffer_context = self.pages.temporary_frames(3)
            self._buffers = self._buffer_context.__enter__()

            self._left_reader = TempPageReader(self._left_path, self._buffers[0])
            self._right_reader = TempPageReader(self._right_path, self._buffers[1])

            self._left_row = self._left_reader.read()
            self._right_row = self._right_reader.read()
            self._group_key = None
            self._group_left = None
            self._opened = True

        except Exception:
            self.close()
            raise

    @staticmethod
    def _key(value: str | float) -> tuple[int, int | float, bytes]:
        if isinstance(value, str):
            return (1, 0, value.encode("utf-8"))
        return (0, value, b"")

    def _finish_group_reader(self) -> None:
        if self._group_reader is not None:
            self._group_reader.close()
            self._counters.page_reads += self._group_reader.page_reads
            self._group_reader = None

    def _start_group(self) -> None:
        """Spill all right rows for the matching key to disk."""
        assert self._right_row is not None
        assert self._group_path is not None
        assert self._buffers is not None

        self._group_key = self._right_row[self._right_index]

        writer = TempPageWriter(self._group_path, self._buffers[2])
        try:
            while (
                self._right_row is not None
                and self._right_row[self._right_index] == self._group_key
            ):
                writer.write(self._right_row)
                assert self._right_reader is not None
                self._right_row = self._right_reader.read()
        finally:
            writer.close()
            self._counters.page_writes += writer.page_writes

        self._group_left = self._left_row
        self._group_reader = TempPageReader(
            self._group_path,
            self._buffers[2],
        )

    def next(self) -> Row | None:
        if not self._opened:
            raise RuntimeError("SortMergeJoin is not open")

        while True:
            if self._group_reader is not None:
                assert self._group_left is not None

                right = self._group_reader.read()
                if right is not None:
                    self._counters.tuples_out += 1
                    return self._group_left + right

                self._finish_group_reader()

                assert self._left_reader is not None
                self._left_row = self._left_reader.read()

                if (
                    self._left_row is not None
                    and self._left_row[self._left_index] == self._group_key
                ):
                    assert self._group_path is not None
                    assert self._buffers is not None

                    self._group_left = self._left_row
                    self._group_reader = TempPageReader(
                        self._group_path,
                        self._buffers[2],
                    )
                    continue

                self._group_left = None
                self._group_key = None
                continue

            if self._left_row is None or self._right_row is None:
                return None

            left_key = self._key(self._left_row[self._left_index])
            right_key = self._key(self._right_row[self._right_index])
            self._counters.comparisons += 1

            if left_key < right_key:
                assert self._left_reader is not None
                self._left_row = self._left_reader.read()
            elif left_key > right_key:
                assert self._right_reader is not None
                self._right_row = self._right_reader.read()
            else:
                self._start_group()

    def close(self) -> None:
        self._finish_group_reader()

        if self._left_reader is not None:
            self._counters.page_reads += self._left_reader.page_reads
            self._left_reader.close()
            self._left_reader = None

        if self._right_reader is not None:
            self._counters.page_reads += self._right_reader.page_reads
            self._right_reader.close()
            self._right_reader = None

        if self._buffer_context is not None:
            self._buffer_context.__exit__(None, None, None)
            self._buffer_context = None
            self._buffers = None

        self.left.close()
        self.right.close()

        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

        self._left_row = None
        self._right_row = None
        self._group_left = None
        self._group_key = None
        self._opened = False
