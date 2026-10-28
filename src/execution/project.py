from src.execution.operator import Operator


class Project(Operator):
    """Select columns from the child operator without removing duplicates."""

    def __init__(self, child: Operator, columns: list[str]) -> None:
        super().__init__()
        self.child = child
        self.columns = columns
        self._indices: list[int] = []
        self._opened = False

    def open(self) -> None:
        self.child.open()

        try:
            self._indices = []

            for column in self.columns:
                matches = [
                    index
                    for index, (name, _) in enumerate(self.child.schema)
                    if name == column
                ]

                if len(matches) != 1:
                    raise ValueError(f"Unknown or ambiguous column: {column}")

                self._indices.append(matches[0])

            self.schema = [self.child.schema[index] for index in self._indices]

            names = [name for name, _ in self.schema]

            if len(names) != len(set(names)):
                raise ValueError("Duplicate projected column names")

        except Exception:
            self.child.close()
            raise

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._opened = True

    def next(self) -> tuple[int | str | float, ...] | None:
        if not self._opened:
            raise RuntimeError("Project is not open")

        row = self.child.next()

        if row is None:
            return None

        projected = tuple(row[index] for index in self._indices)
        self._counters.tuples_out += 1

        return projected

    def close(self) -> None:
        self.child.close()
        self._opened = False
