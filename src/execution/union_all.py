from src.execution.operator import Operator


class UnionAll(Operator):
    """Concatenate two compatible input streams, preserving duplicates."""

    def __init__(self, left: Operator, right: Operator) -> None:
        super().__init__()
        self.left = left
        self.right = right
        self._reading_left = True
        self._opened = False

    def open(self) -> None:
        self.left.open()

        try:
            self.right.open()

            left_types = [column_type for _, column_type in self.left.schema]
            right_types = [column_type for _, column_type in self.right.schema]

            if left_types != right_types:
                raise ValueError("UnionAll requires matching column types")

            self.schema = list(self.left.schema)

        except Exception:
            self.right.close()
            self.left.close()
            raise

        self._reading_left = True
        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._opened = True

    def next(self) -> tuple[int | str | float, ...] | None:
        if not self._opened:
            raise RuntimeError("UnionAll is not open")

        if self._reading_left:
            row = self.left.next()

            if row is not None:
                self._counters.tuples_out += 1
                return row

            self._reading_left = False

        row = self.right.next()

        if row is not None:
            self._counters.tuples_out += 1

        return row

    def close(self) -> None:
        self.left.close()
        self.right.close()
        self._reading_left = True
        self._opened = False
