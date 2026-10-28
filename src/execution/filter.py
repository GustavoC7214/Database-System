from typing import TypeVar

from src.execution.column_resolver import resolve_column
from src.execution.operator import Operator

T = TypeVar("T", int, float, bytes)


class Filter(Operator):
    """Return only rows satisfying a comparison condition."""

    def __init__(
        self,
        child: Operator,
        column: str,
        comparison: str,
        value: int | str,
    ) -> None:
        super().__init__()
        self.child = child
        self.column = column
        self.comparison = comparison
        self.value = value
        self._column_index = -1
        self._opened = False

    def open(self) -> None:
        self.child.open()

        try:
            self.schema = list(self.child.schema)

            self._column_index = resolve_column(self.schema, self.column)

            if self.comparison not in {"=", "!=", "<", "<=", ">", ">="}:
                raise ValueError(f"Unsupported comparison: {self.comparison}")

            column_type = self.schema[self._column_index][1]

            if column_type == "INT":
                valid_type = type(self.value) is int
            elif column_type.startswith("VARCHAR("):
                valid_type = isinstance(self.value, str)
            else:
                raise ValueError(f"Unsupported column type: {column_type}")

            if not valid_type:
                raise ValueError(f"Comparison value has wrong type for {self.column}")

        except Exception:
            self.child.close()
            raise

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._opened = True

    def _matches(self, actual: str | float) -> bool:
        expected = self.value

        if isinstance(actual, str) and isinstance(expected, str):
            return self._compare(
                actual.encode("utf-8"),
                expected.encode("utf-8"),
            )

        if type(actual) is int and type(expected) is int:
            return self._compare(actual, expected)

        if type(actual) is float and type(expected) is float:
            return self._compare(actual, expected)

        raise TypeError("Cannot compare values of different types")

    def _compare(self, left: T, right: T) -> bool:
        if self.comparison == "=":
            return left == right
        if self.comparison == "!=":
            return left != right
        if self.comparison == "<":
            return left < right
        if self.comparison == "<=":
            return left <= right
        if self.comparison == ">":
            return left > right
        return left >= right

    def next(self) -> tuple[int | str | float, ...] | None:
        if not self._opened:
            raise RuntimeError("Filter is not open")

        while (row := self.child.next()) is not None:
            self._counters.comparisons += 1

            if self._matches(row[self._column_index]):
                self._counters.tuples_out += 1
                return row

        return None

    def close(self) -> None:
        self.child.close()
        self._opened = False
