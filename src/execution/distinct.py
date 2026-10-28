"""Duplicate elimination using external sort or disk-backed hashing."""

from src.execution.hash_distinct import HashDistinct
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.sort import Sort


class Distinct(Operator):
    """Return one copy of each tuple."""

    def __init__(
        self,
        child: Operator,
        pages: SharedPageManager,
        mode: str = "sort",
    ) -> None:
        super().__init__()

        if mode not in {"sort", "hash"}:
            raise ValueError("Distinct mode must be 'sort' or 'hash'")

        self.child = child
        self.pages = pages
        self.mode = mode

        self._sort: Sort | None = None
        self._hash: HashDistinct | None = None
        self._previous: tuple | None = None
        self._opened = False
        self._sort_page_reads = 0
        self._sort_page_writes = 0

    def open(self) -> None:
        self.close()

        self._counters.tuples_out = 0
        self._counters.comparisons = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._sort_page_reads = 0
        self._sort_page_writes = 0

        if self.mode == "hash":
            self._hash = HashDistinct(self.child, self.pages)

            try:
                self._hash.open()
                self.schema = list(self._hash.schema)
            except Exception:
                self.close()
                raise

            self._opened = True
            return

        self.child.open()

        try:
            self.schema = list(self.child.schema)
            keys = [(name, "asc") for name, _ in self.schema]

            self._sort = Sort(self.child, keys, self.pages)
            self._sort.open(child_already_open=True)
        except Exception:
            self.close()
            raise

        self._previous = None
        self._opened = True

    def next(self) -> tuple | None:
        if not self._opened:
            raise RuntimeError("Distinct is not open")

        if self._hash is not None:
            return self._hash.next()

        if self._sort is None:
            raise RuntimeError("Distinct sort is not initialized")

        while (row := self._sort.next()) is not None:
            if self._previous is not None:
                self._counters.comparisons += 1

                if row == self._previous:
                    continue

            self._previous = row
            self._counters.tuples_out += 1
            return row

        return None

    def counters(self) -> dict[str, int]:
        if self._hash is not None:
            return self._hash.counters()

        result = super().counters()

        if self._sort is not None:
            sort_counts = self._sort.counters()
            result["page_reads"] += sort_counts["page_reads"]
            result["page_writes"] += sort_counts["page_writes"]
        else:
            result["page_reads"] += self._sort_page_reads
            result["page_writes"] += self._sort_page_writes

        return result

    def close(self) -> None:
        if self._hash is not None:
            hash_counts = self._hash.counters()
            self._hash.close()
            self._counters.tuples_out = hash_counts["tuples_out"]
            self._counters.comparisons = hash_counts["comparisons"]
            self._counters.page_reads = hash_counts["page_reads"]
            self._counters.page_writes = hash_counts["page_writes"]
            self._hash = None

        if self._sort is not None:
            sort_counts = self._sort.counters()
            self._sort_page_reads = sort_counts["page_reads"]
            self._sort_page_writes = sort_counts["page_writes"]
            self._sort.close()
            self._sort = None

        self._opened = False
        self._previous = None
