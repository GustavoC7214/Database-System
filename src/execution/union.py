"""Set union using bag union followed by external distinct."""

from src.execution.distinct import Distinct
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.union_all import UnionAll


class Union(Distinct):
    def __init__(
        self,
        left: Operator,
        right: Operator,
        pages: SharedPageManager,
    ) -> None:
        super().__init__(
            UnionAll(left, right),
            pages,
            mode="sort",
        )
