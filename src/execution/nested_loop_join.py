"""Block nested-loop equijoin with a shared four-frame budget."""

import tempfile
from pathlib import Path

from src.execution.column_resolver import resolve_column
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter
from src.execution.temp_run import tuple_size
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]


class NestedLoopJoin(Operator):
    """Join two inputs using bounded outer blocks and inner rescans."""

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
        self._inner_path: Path | None = None
        self._outer_path: Path | None = None
        self._inner_reader: TempPageReader | None = None
        self._outer_reader: TempPageReader | None = None
        self._buffers = None
        self._buffer_context = None

        self._left_index = -1
        self._right_index = -1
        self._outer_block: list[Row] = []
        self._pending_outer: Row | None = None
        self._current_inner: Row | None = None
        self._outer_position = 0
        self._outer_finished = False
        self._opened = False

    @staticmethod
    def _column_index(
        schema: list[tuple[str, str]],
        column: str,
    ) -> int:
        return resolve_column(schema, column)

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0

        try:
            self.left.open()

            self._left_index = self._column_index(self.left.schema, self.left_key)

            self._directory = tempfile.TemporaryDirectory(
                prefix="execution_nested_loop_join_"
            )
            root = Path(self._directory.name)

            self._outer_path = root / "outer.tmp"
            self._inner_path = root / "inner.tmp"

            # Materialize the outer input before opening the right input.
            # This prevents nested operators from holding frames
            # simultaneously during the join phase.
            with self.pages.temporary_frames(1) as buffers:
                writer = TempPageWriter(self._outer_path, buffers[0])

                try:
                    while (row := self.left.next()) is not None:
                        writer.write(row)
                finally:
                    writer.close()
                    self._counters.page_writes += writer.page_writes

            self.left.close()

            self.right.open()

            self._right_index = self._column_index(self.right.schema, self.right_key)
            self.schema = list(self.left.schema) + list(self.right.schema)

            # Materialize the inner input.
            with self.pages.temporary_frames(1) as buffers:
                writer = TempPageWriter(self._inner_path, buffers[0])

                try:
                    while (row := self.right.next()) is not None:
                        writer.write(row)
                finally:
                    writer.close()
                    self._counters.page_writes += writer.page_writes

            self.right.close()

            # All child operators are now closed.
            # Reserve B-1 frames: B-2 outer frames and one inner frame.
            # The remaining frame stays available for output or other work.
            self._buffer_context = self.pages.temporary_frames(self.pages.capacity - 1)
            self._buffers = self._buffer_context.__enter__()

            self._outer_reader = TempPageReader(
                self._outer_path,
                self._buffers[0],
            )

            self._outer_block = []
            self._pending_outer = None
            self._current_inner = None
            self._outer_position = 0
            self._outer_finished = False
            self._opened = True

        except Exception:
            self.close()
            raise

    def _load_outer_block(self) -> bool:
        self._outer_block = []
        used_bytes = 0
        limit = (self.pages.capacity - 2) * PAGE_SIZE

        while used_bytes < limit:
            row = self._pending_outer
            self._pending_outer = None

            if row is None:
                assert self._outer_reader is not None
                row = self._outer_reader.read()

            if row is None:
                self._outer_finished = True
                break

            size = tuple_size(row)
            if size > limit:
                raise ValueError(
                    "Outer tuple exceeds the available outer-block capacity"
                )

            if self._outer_block and used_bytes + size > limit:
                self._pending_outer = row
                break

            self._outer_block.append(row)
            used_bytes += size

        return bool(self._outer_block)

    def _open_inner_reader(self) -> None:
        assert self._inner_path is not None
        assert self._buffers is not None

        if self._inner_reader is not None:
            self._inner_reader.close()
            self._counters.page_reads += self._inner_reader.page_reads

        self._inner_reader = TempPageReader(
            self._inner_path,
            self._buffers[-1],
        )

    def next(self) -> Row | None:
        if not self._opened:
            raise RuntimeError("NestedLoopJoin is not open")

        while True:
            if not self._outer_block:
                if not self._load_outer_block():
                    return None

                self._open_inner_reader()
                self._current_inner = None
                self._outer_position = 0

            assert self._inner_reader is not None

            if self._current_inner is None:
                self._current_inner = self._inner_reader.read()
                self._outer_position = 0

                if self._current_inner is None:
                    self._inner_reader.close()
                    self._counters.page_reads += self._inner_reader.page_reads
                    self._inner_reader = None
                    self._outer_block = []
                    continue

            while self._outer_position < len(self._outer_block):
                outer = self._outer_block[self._outer_position]
                self._outer_position += 1
                self._counters.comparisons += 1

                if outer[self._left_index] == self._current_inner[self._right_index]:
                    self._counters.tuples_out += 1
                    return outer + self._current_inner

            self._current_inner = None

    def close(self) -> None:
        if self._outer_reader is not None:
            self._outer_reader.close()
            self._counters.page_reads += self._outer_reader.page_reads
            self._outer_reader = None

        if self._inner_reader is not None:
            self._inner_reader.close()
            self._counters.page_reads += self._inner_reader.page_reads
            self._inner_reader = None

        if self._buffer_context is not None:
            self._buffer_context.__exit__(None, None, None)
            self._buffer_context = None
            self._buffers = None

        self.left.close()
        self.right.close()

        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

        self._inner_path = None
        self._outer_block = []
        self._pending_outer = None
        self._current_inner = None
        self._opened = False
        self._outer_path = None
