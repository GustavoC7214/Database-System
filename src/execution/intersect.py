"""Set intersection with distinct semantics."""

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.set_operation import SortedSetOperation


class Intersect(SortedSetOperation):
    """Return distinct tuples present in both inputs."""

    def __init__(
        self,
        left: Operator,
        right: Operator,
        pages: SharedPageManager,
    ) -> None:
        super().__init__(left, right, pages, "intersect")
