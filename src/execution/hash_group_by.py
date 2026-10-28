"""Disk-backed hash grouping with sort fallback for oversized partitions."""

import hashlib
import json
import tempfile
from collections.abc import Generator
from pathlib import Path

from src.execution.hash_distinct import _PartitionScan
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter
from src.execution.temp_run import tuple_size
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]
AggregateSpec = tuple[str, int | None]
State = tuple[
    int,
    list[float],
    list[int | str | float | None],
    list[int | str | float | None],
]


class HashGroupBy(Operator):
    """Aggregate hash partitions, falling back to external sorting."""

    def __init__(
        self,
        child: Operator,
        key_indices: list[int],
        aggregate_specs: list[AggregateSpec],
        pages: SharedPageManager,
        output_schema: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.child = child
        self.key_indices = list(key_indices)
        self.aggregate_specs = list(aggregate_specs)
        self.pages = pages
        self.schema = list(output_schema)
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._partitions: list[Path] = []
        self._iterator: Generator[Row, None, None] | None = None
        self._opened = False
        self._empty_global_emitted = False

    def _key(self, row: Row) -> tuple:
        return tuple(row[index] for index in self.key_indices)

    @staticmethod
    def _partition_index(key: tuple, count: int) -> int:
        encoded = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        digest = hashlib.blake2b(encoded, digest_size=8).digest()
        return int.from_bytes(digest, "big") % count

    def open(self, child_already_open: bool = False) -> None:
        if self._opened or self._directory is not None:
            self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._empty_global_emitted = False

        try:
            if not child_already_open:
                self.child.open()

            self._directory = tempfile.TemporaryDirectory(
                prefix="execution_hash_group_by_"
            )
            root = Path(self._directory.name)
            count = self.pages.capacity - 1
            self._partitions = [root / f"partition_{i}.tmp" for i in range(count)]

            # B-1 output frames, leaving one for the child scan.
            with self.pages.temporary_frames(count) as buffers:
                writers = [
                    TempPageWriter(path, buffer)
                    for path, buffer in zip(self._partitions, buffers, strict=True)
                ]
                try:
                    while (row := self.child.next()) is not None:
                        index = self._partition_index(self._key(row), count)
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

    @staticmethod
    def _compare_values(
        left: str | float,
        right: str | float,
        *,
        minimum: bool,
    ) -> bool:
        if isinstance(left, str) and isinstance(right, str):
            return left < right if minimum else left > right

        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right if minimum else left > right

        raise TypeError("Cannot compare incompatible aggregate types")

    def _new_state(self) -> State:
        length = len(self.aggregate_specs)
        return (
            0,
            [0] * length,
            [None] * length,
            [None] * length,
        )

    def _update(self, state: State, row: Row) -> State:
        count, totals, minima, maxima = state
        count += 1

        for i, (function, index) in enumerate(self.aggregate_specs):
            if index is None:
                continue

            value = row[index]

            if function in {"sum", "avg"}:
                if not isinstance(value, (int, float)):
                    raise TypeError(f"{function.upper()} requires a numeric column")
                totals[i] += value

            elif function == "min":
                current_min = minima[i]
                if current_min is None or self._compare_values(
                    value, current_min, minimum=True
                ):
                    minima[i] = value

            elif function == "max":
                current_max = maxima[i]
                if current_max is None or self._compare_values(
                    value, current_max, minimum=False
                ):
                    maxima[i] = value

        return count, totals, minima, maxima

    def _result(self, key: tuple, state: State) -> Row:
        count, totals, minima, maxima = state
        values: list[int | str | float] = list(key)

        for i, (function, _) in enumerate(self.aggregate_specs):
            if function == "count":
                values.append(count)
            elif function == "sum":
                values.append(totals[i])
            elif function == "avg":
                values.append(round(totals[i] / count, 4))
            elif function == "min":
                minimum = minima[i]
                assert minimum is not None
                values.append(minimum)
            elif function == "max":
                maximum = maxima[i]
                assert maximum is not None
                values.append(maximum)

        return tuple(values)

    def _fallback(self, path: Path) -> Generator[Row, None, None]:
        # Import here to avoid a module-level circular import.
        from src.execution.group_by import GroupBy

        scan = _PartitionScan(path, self.child.schema)
        keys = [self.child.schema[i][0] for i in self.key_indices]
        aggregates = [
            (
                function,
                "*" if index is None else self.child.schema[index][0],
            )
            for function, index in self.aggregate_specs
        ]
        fallback = GroupBy(scan, keys, aggregates, self.pages, mode="sort")

        try:
            fallback.open()
            while (row := fallback.next()) is not None:
                yield row
        finally:
            counts = fallback.counters()
            self._counters.page_reads += counts["page_reads"]
            self._counters.page_writes += counts["page_writes"]
            self._counters.comparisons += counts["comparisons"]
            fallback.close()

    def _emit_partitions(self) -> Generator[Row, None, None]:
        memory_limit = (self.pages.capacity - 2) * PAGE_SIZE

        for path in self._partitions:
            groups: dict[tuple, State] = {}
            used_bytes = 0
            overflow = False

            with (
                self.pages.temporary_frames(1) as buffers,
                TempPageReader(path, buffers[0]) as reader,
            ):
                while (row := reader.read()) is not None:
                    key = self._key(row)
                    self._counters.comparisons += 1

                    if key not in groups:
                        # Logical estimate for the grouping key and
                        # its aggregate state.
                        estimated = (
                            tuple_size(key) + 64 + 32 * len(self.aggregate_specs)
                        )
                        if used_bytes + estimated > memory_limit:
                            overflow = True
                            break

                        groups[key] = self._new_state()
                        used_bytes += estimated

                    groups[key] = self._update(groups[key], row)

                self._counters.page_reads += reader.page_reads

            if overflow:
                groups.clear()
                yield from self._fallback(path)
            else:
                for key, state in groups.items():
                    yield self._result(key, state)

    def next(self) -> Row | None:
        if not self._opened or self._iterator is None:
            raise RuntimeError("HashGroupBy is not open")

        row = next(self._iterator, None)

        if row is None and not self.key_indices and not self._empty_global_emitted:
            self._empty_global_emitted = True

            if self._counters.tuples_out == 0:
                if any(function != "count" for function, _ in self.aggregate_specs):
                    raise ValueError("Aggregate undefined for empty global group")
                row = tuple(0 for _ in self.aggregate_specs)

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
