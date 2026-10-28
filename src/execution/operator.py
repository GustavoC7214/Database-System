from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OperatorCounters:
    tuples_out: int = 0
    comparisons: int = 0
    page_reads: int = 0
    page_writes: int = 0


class Operator(ABC):
    """Base interface for all Module 2 execution operators."""

    def __init__(self) -> None:
        self.schema: list[tuple[str, str]] = []
        self._counters = OperatorCounters()

    @abstractmethod
    def open(self) -> None:
        """Prepare the operator for execution."""

    @abstractmethod
    def next(self) -> tuple[int | str | float, ...] | None:
        """Return the next tuple, or None at end of stream."""

    @abstractmethod
    def close(self) -> None:
        """Release all resources owned by this operator."""

    def counters(self) -> dict[str, int]:
        """Return this operator's own execution statistics."""
        return {
            "tuples_out": self._counters.tuples_out,
            "comparisons": self._counters.comparisons,
            "page_reads": self._counters.page_reads,
            "page_writes": self._counters.page_writes,
        }
