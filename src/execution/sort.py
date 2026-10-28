import tempfile
from collections.abc import Generator
from pathlib import Path

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.run_generation import Row, generate_sorted_runs
from src.execution.run_merge import merge_runs, merge_to_temp_run
from src.execution.temp_page_reader import TempPageReader


class Sort(Operator):
    """External merge sort over a child operator."""

    def __init__(
        self,
        child: Operator,
        keys: list[tuple[str, str]],
        pages: SharedPageManager,
    ) -> None:
        super().__init__()
        self.child = child
        self.keys = keys
        self.pages = pages

        self._opened = False
        self._key_indices: list[int] = []
        self._directions: list[str] = []
        self._iterator: Generator[Row, None, None] | None = None
        self._temp_directory: tempfile.TemporaryDirectory[str] | None = None
        self._final_reader: TempPageReader | None = None
        # Measurements of the actual external-sort execution.
        self.initial_run_count = 0
        self.intermediate_merge_passes = 0
        self.final_merge_passes = 0

    def _sort_key(self, row: Row) -> tuple:
        result = []

        for index, direction in zip(
            self._key_indices,
            self._directions,
            strict=True,
        ):
            value = row[index]

            if isinstance(value, str):
                comparable = value.encode("utf-8")
            else:
                comparable = value

            if direction == "DESC":
                if isinstance(comparable, (int, float)):
                    comparable = -comparable
                else:
                    comparable = tuple(-byte for byte in comparable) + (256,)

            result.append(comparable)

        return tuple(result)

    def _record_page_writes(self, count: int) -> None:
        self._counters.page_writes += count

    def _record_page_reads(self, count: int) -> None:
        self._counters.page_reads += count

    def open(self, child_already_open: bool = False) -> None:
        if not child_already_open:
            self.child.open()

        try:
            self.schema = list(self.child.schema)
            self._key_indices = []
            self._directions = []

            for column, direction in self.keys:
                matches = [
                    index
                    for index, (name, _) in enumerate(self.schema)
                    if name == column
                ]

                if len(matches) != 1:
                    raise ValueError(f"Unknown or ambiguous sort column: {column}")

                direction = direction.upper()

                if direction not in {"ASC", "DESC"}:
                    raise ValueError(f"Unsupported sort direction: {direction}")

                self._key_indices.append(matches[0])
                self._directions.append(direction)

            self._temp_directory = tempfile.TemporaryDirectory(prefix="execution_sort_")
            temp_path = Path(self._temp_directory.name)

            self._counters.tuples_out = 0
            self.initial_run_count = 0
            self.intermediate_merge_passes = 0
            self.final_merge_passes = 0
            self._counters.comparisons = 0
            self._counters.page_reads = 0
            self._counters.page_writes = 0

            runs = generate_sorted_runs(
                self.child,
                self.pages.capacity,
                self._sort_key,
                temp_path,
                on_page_write=self._record_page_writes,
                pages=self.pages,
            )
            self.initial_run_count = len(runs)

            fan_in = self.pages.capacity - 1

            while len(runs) > fan_in:
                self.intermediate_merge_passes += 1
                merged_runs = []

                for start in range(0, len(runs), fan_in):
                    group = runs[start : start + fan_in]

                    if len(group) == 1:
                        merged_runs.append(group[0])
                        continue

                    merged_path = merge_to_temp_run(
                        group,
                        self._sort_key,
                        temp_path,
                        on_page_read=self._record_page_reads,
                        on_page_write=self._record_page_writes,
                        pages=self.pages,
                    )

                    merged_runs.append(merged_path)

                    for path in group:
                        path.unlink()

                runs = merged_runs

            if len(runs) == 1:
                self.final_merge_passes = 0
                self._final_reader = TempPageReader(runs[0])
                self._iterator = None
            else:
                self.final_merge_passes = 1 if runs else 0
                self._final_reader = None
                self._iterator = merge_runs(
                    runs,
                    self._sort_key,
                    on_page_read=self._record_page_reads,
                    pages=self.pages,
                )

            self._opened = True

        except Exception:
            self.close()
            raise

    def next(self) -> Row | None:
        if not self._opened:
            raise RuntimeError("Sort operator is not open")

        if self._final_reader is not None:
            before = self._final_reader.page_reads
            row = self._final_reader.read()
            self._record_page_reads(self._final_reader.page_reads - before)
        elif self._iterator is not None:
            row = next(self._iterator, None)
        else:
            row = None

        if row is not None:
            self._counters.tuples_out += 1

        return row

    def close(self) -> None:
        if self._final_reader is not None:
            self._final_reader.close()
            self._final_reader = None

        if self._iterator is not None:
            self._iterator.close()
            self._iterator = None

        if self._temp_directory is not None:
            self._temp_directory.cleanup()
            self._temp_directory = None

        self.child.close()
        self._opened = False
