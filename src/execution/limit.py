from src.execution.operator import Operator


class Limit(Operator):
    """Return at most N tuples without pulling unnecessary child tuples."""

    def __init__(self, child: Operator, count: int) -> None:
        super().__init__()
        if type(count) is not int or count < 0:
            raise ValueError("Limit count must be a nonnegative integer")

        self.child = child
        self.count = count
        self._opened = False

    def open(self) -> None:
        self.child.open()
        self.schema = list(self.child.schema)

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._opened = True

    def next(self) -> tuple[int | str | float, ...] | None:
        if not self._opened:
            raise RuntimeError("Limit is not open")

        if self._counters.tuples_out >= self.count:
            return None

        row = self.child.next()

        if row is None:
            return None

        self._counters.tuples_out += 1
        return row

    def close(self) -> None:
        self.child.close()
        self._opened = False
