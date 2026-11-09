"""Sort-based grouping and aggregation."""

from src.execution.hash_group_by import HashGroupBy
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.sort import Sort

Row = tuple[int | str | float, ...]


class GroupBy(Operator):
    """Group input tuples and compute aggregate values."""

    def __init__(
        self,
        child: Operator,
        keys: list[str],
        aggregates: list[tuple[str, str] | tuple[str, str, str]],
        pages: SharedPageManager,
        mode: str = "sort",
    ) -> None:
        super().__init__()

        if mode not in {"sort", "hash"}:
            raise ValueError("GroupBy mode must be 'sort' or 'hash'")

        self.child = child
        self.keys = keys
        self.aggregates = aggregates
        self.pages = pages
        self.mode = mode

        self._sort: Sort | None = None
        self._hash: HashGroupBy | None = None
        self._source: Operator | None = None
        self._key_indices: list[int] = []
        self._aggregate_specs: list[tuple[str, int | None]] = []
        self._pending: Row | None = None
        self._finished = False
        self._opened = False
        self._saved_reads = 0
        self._saved_writes = 0

    def _prepare_schema(self) -> None:
        columns = self.child.schema
        self._key_indices = []
        self._aggregate_specs = []

        for name in self.keys:
            matches = [i for i, (column, _) in enumerate(columns) if column == name]
            if len(matches) != 1:
                raise ValueError(f"Unknown or ambiguous grouping column: {name}")
            self._key_indices.append(matches[0])

        result = [columns[i] for i in self._key_indices]

        for aggregate in self.aggregates:
            if len(aggregate) == 2:
                function, column = aggregate
                explicit_name = None
            elif len(aggregate) == 3:
                function, column, explicit_name = aggregate
                if not isinstance(explicit_name, str) or not explicit_name:
                    raise ValueError("Aggregate output name must be a nonempty string")
            else:
                raise ValueError("Aggregate must contain 2 or 3 fields")

            function = function.lower()

            if function not in {"count", "sum", "avg", "min", "max"}:
                raise ValueError(f"Unsupported aggregate: {function}")

            if column == "*":
                if function != "count":
                    raise ValueError("Only COUNT supports the '*' argument")
                index = None
                column_type = "INT"
                output_name = "count_star"
            else:
                matches = [i for i, (name, _) in enumerate(columns) if name == column]
                if len(matches) != 1:
                    raise ValueError(f"Unknown or ambiguous aggregate column: {column}")

                index = matches[0]
                source_type = columns[index][1]

                if function in {"sum", "avg"} and (source_type.upper() != "INT"):
                    raise ValueError(f"{function.upper()} requires an INT column")

                column_type = (
                    "REAL"
                    if function == "avg"
                    else "INT"
                    if function in {"count", "sum"}
                    else source_type
                )
                output_name = f"{function}_{column.replace('.', '_')}"

            if explicit_name is not None:
                output_name = explicit_name

            self._aggregate_specs.append((function, index))
            result.append((output_name, column_type))

        self.schema = result

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._saved_reads = 0
        self._saved_writes = 0

        try:
            self.child.open()
            self._prepare_schema()

            if self.mode == "hash":
                self._hash = HashGroupBy(
                    self.child,
                    self._key_indices,
                    self._aggregate_specs,
                    self.pages,
                    self.schema,
                )
                self._hash.open(child_already_open=True)
                self._opened = True
                return

            if self.keys:
                sort_keys = [(key, "asc") for key in self.keys]
                self._sort = Sort(self.child, sort_keys, self.pages)
                self._sort.open(child_already_open=True)
                self._source = self._sort
            else:
                self._source = self.child

            self._pending = None
            self._finished = False
            self._opened = True
        except Exception:
            self.close()
            raise

    def _group_key(self, row: Row) -> tuple:
        return tuple(row[i] for i in self._key_indices)

    def _aggregate_rows(self, first: Row) -> Row:
        assert self._source is not None

        group_key = self._group_key(first)
        count = 0
        totals: list[int | float] = [0] * len(self._aggregate_specs)
        minima: list[int | str | float | None] = [None] * len(self._aggregate_specs)
        maxima: list[int | str | float | None] = [None] * len(self._aggregate_specs)

        row: Row | None = first

        while row is not None:
            count += 1

            for i, (function, index) in enumerate(self._aggregate_specs):
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

            following = self._source.next()

            if following is None:
                self._finished = True
                break

            self._counters.comparisons += 1

            if self._group_key(following) != group_key:
                self._pending = following
                break

            row = following

        values: list[int | str | float] = list(group_key)

        for i, (function, _) in enumerate(self._aggregate_specs):
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

    def next(self) -> Row | None:
        if self.mode == "hash":
            if not self._opened or self._hash is None:
                raise RuntimeError("GroupBy is not open")

            row = self._hash.next()
            if row is not None:
                self._counters.tuples_out += 1
            return row
        if not self._opened or self._source is None:
            raise RuntimeError("GroupBy is not open")

        if self._finished and self._pending is None:
            return None

        first = self._pending
        self._pending = None

        if first is None:
            first = self._source.next()

        if first is None:
            self._finished = True

            if not self.keys and self._counters.tuples_out == 0:
                if any(function != "count" for function, _ in self._aggregate_specs):
                    raise ValueError("Aggregate undefined for empty global group")

                self._counters.tuples_out += 1
                return tuple(0 for _ in self._aggregate_specs)

            return None

        result = self._aggregate_rows(first)
        self._counters.tuples_out += 1
        return result

    def counters(self) -> dict[str, int]:
        result = super().counters()

        if self._hash is not None:
            counts = self._hash.counters()
            result["comparisons"] += counts["comparisons"]
            result["page_reads"] += counts["page_reads"]
            result["page_writes"] += counts["page_writes"]
            return result

        if self._sort is not None:
            counts = self._sort.counters()
            result["page_reads"] += counts["page_reads"]
            result["page_writes"] += counts["page_writes"]
        else:
            result["page_reads"] += self._saved_reads
            result["page_writes"] += self._saved_writes

        return result

    def close(self) -> None:
        if self._hash is not None:
            counts = self._hash.counters()
            self._counters.comparisons += counts["comparisons"]
            self._counters.page_reads += counts["page_reads"]
            self._counters.page_writes += counts["page_writes"]
            self._hash.close()
            self._hash = None

        if self._sort is not None:
            counts = self._sort.counters()
            self._saved_reads = counts["page_reads"]
            self._saved_writes = counts["page_writes"]
            self._sort.close()
            self._sort = None
        else:
            self.child.close()

        self._source = None
        self._pending = None
        self._finished = False
        self._opened = False

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
