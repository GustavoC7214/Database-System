"""Set difference with distinct semantics."""

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.set_operation import SortedSetOperation


class Except(SortedSetOperation):
    """Return distinct left tuples absent from the right input."""

    def __init__(
        self,
        left: Operator,
        right: Operator,
        pages: SharedPageManager,
    ) -> None:
        super().__init__(left, right, pages, "except")
