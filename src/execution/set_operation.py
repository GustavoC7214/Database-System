"""Shared external-sort implementation for binary set operations."""

import tempfile
from pathlib import Path

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.sort import Sort
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter

Row = tuple[int | str | float, ...]


class SortedSetOperation(Operator):
    """Merge two externally sorted relations with distinct semantics."""

    def __init__(
        self,
        left: Operator,
        right: Operator,
        pages: SharedPageManager,
        operation: str,
    ) -> None:
        super().__init__()

        if operation not in {"intersect", "except"}:
            raise ValueError("Invalid set operation")

        self.left = left
        self.right = right
        self.pages = pages
        self.operation = operation

        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._left_reader: TempPageReader | None = None
        self._right_reader: TempPageReader | None = None
        self._buffer_context = None
        self._buffers = None

        self._left_row: Row | None = None
        self._right_row: Row | None = None
        self._previous_output: Row | None = None
        self._opened = False

    @staticmethod
    def _validate_schemas(
        left_schema: list[tuple[str, str]],
        right_schema: list[tuple[str, str]],
    ) -> None:
        if len(left_schema) != len(right_schema):
            raise ValueError("Set operations require the same number of columns")

        for (_, left_type), (_, right_type) in zip(
            left_schema, right_schema, strict=True
        ):
            if left_type.lower() != right_type.lower():
                raise ValueError("Set operations require matching column types")

    def _materialize_sorted(
        self,
        child: Operator,
        path: Path,
    ) -> None:
        keys = [(name, "asc") for name, _ in child.schema]
        sorter = Sort(child, keys, self.pages)

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
            self.left.open()
            self.right.open()

            self._validate_schemas(self.left.schema, self.right.schema)
            self.schema = list(self.left.schema)

            self.left.close()
            self.right.close()

            self._directory = tempfile.TemporaryDirectory(
                prefix=f"execution_{self.operation}_"
            )
            root = Path(self._directory.name)
            left_path = root / "left.tmp"
            right_path = root / "right.tmp"

            self._materialize_sorted(self.left, left_path)
            self._materialize_sorted(self.right, right_path)

            self._buffer_context = self.pages.temporary_frames(2)
            self._buffers = self._buffer_context.__enter__()

            self._left_reader = TempPageReader(left_path, self._buffers[0])
            self._right_reader = TempPageReader(right_path, self._buffers[1])

            self._left_row = self._left_reader.read()
            self._right_row = self._right_reader.read()
            self._previous_output = None
            self._opened = True

        except Exception:
            self.close()
            raise

    def _advance_left(self) -> None:
        assert self._left_reader is not None
        self._left_row = self._left_reader.read()

    def _advance_right(self) -> None:
        assert self._right_reader is not None
        self._right_row = self._right_reader.read()

    def next(self) -> Row | None:
        if not self._opened:
            raise RuntimeError(f"{self.operation} is not open")

        while self._left_row is not None:
            left = self._left_row

            # Suppress duplicates already emitted.
            if self._previous_output is not None and left == self._previous_output:
                self._counters.comparisons += 1
                self._advance_left()
                continue

            # Advance the right side past smaller values.
            while self._right_row is not None and self._right_row < left:
                self._counters.comparisons += 1
                self._advance_right()

            matches = self._right_row is not None and left == self._right_row
            self._counters.comparisons += 1

            self._advance_left()

            should_emit = matches if self.operation == "intersect" else not matches

            if should_emit:
                self._previous_output = left
                self._counters.tuples_out += 1
                return left

        return None

    def close(self) -> None:
        if self._left_reader is not None:
            self._left_reader.close()
            self._counters.page_reads += self._left_reader.page_reads
            self._left_reader = None

        if self._right_reader is not None:
            self._right_reader.close()
            self._counters.page_reads += self._right_reader.page_reads
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
        self._previous_output = None
        self._opened = False
