"""Build physical execution-operator trees from JSON plans."""

import json
from pathlib import Path
from typing import Any, ClassVar

from src.execution.distinct import Distinct
from src.execution.except_operator import Except
from src.execution.filter import Filter
from src.execution.grace_hash_join import GraceHashJoin
from src.execution.group_by import GroupBy
from src.execution.intersect import Intersect
from src.execution.limit import Limit
from src.execution.nested_loop_join import NestedLoopJoin
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.project import Project
from src.execution.seq_scan import SeqScan
from src.execution.sort import Sort
from src.execution.sort_merge_join import SortMergeJoin
from src.execution.union import Union
from src.execution.union_all import UnionAll
from src.parser.ast import (
    AttributeReference,
    Comparison,
    ComparisonOperator,
    NumberLiteral,
    StringLiteral,
)
from src.parser.parser import parse_condition_text


class PhysicalPlanBuilder:
    """Construct an execution tree using one shared page manager."""

    OPERATOR_NAMES: ClassVar[dict[str, str]] = {
        "seqscan": "SeqScan",
        "filter": "Filter",
        "project": "Project",
        "limit": "Limit",
        "sort": "Sort",
        "distinct": "Distinct",
        "group_by": "GroupBy",
        "nested_loop_join": "NestedLoopJoin",
        "sort_merge_join": "SortMergeJoin",
        "hash_join": "GraceHashJoin",
        "union_all": "UnionAll",
        "union": "Union",
        "intersect": "Intersect",
        "except": "Except",
    }

    def __init__(
        self,
        db_dir: str | Path,
        pages: SharedPageManager,
    ) -> None:
        self.db_dir = Path(db_dir)
        self.pages = pages

    @staticmethod
    def _field(node: dict, name: str) -> Any:
        if name not in node:
            raise ValueError(f"Missing plan field: {name}")
        return node[name]

    def _child(self, node: dict) -> Operator:
        return self.build(self._field(node, "child"))

    def _children(self, node: dict) -> tuple[Operator, Operator]:
        return (
            self.build(self._field(node, "left")),
            self.build(self._field(node, "right")),
        )

    def build(self, node: dict) -> Operator:
        if not isinstance(node, dict):
            raise TypeError("Physical plan node must be an object")

        operation = self._field(node, "op")

        if not isinstance(operation, str):
            raise TypeError("Node: field 'op' must be a string")

        operation = self.OPERATOR_NAMES.get(operation, operation)

        if operation == "SeqScan":
            return SeqScan(
                self.db_dir,
                self._field(node, "table"),
                self.pages,
            )

        if operation == "Filter":
            if "condition" in node:
                column, comparison, value = self._parse_filter_condition(
                    node["condition"]
                )
            else:
                column = self._field(node, "column")
                comparison = self._field(node, "comparison")
                value = self._field(node, "value")

            return Filter(
                self._child(node),
                column,
                comparison,
                value,
            )

        if operation == "Project":
            return Project(
                self._child(node),
                self._field(node, "columns"),
                outputs=node.get("outputs"),
            )

        if operation == "Limit":
            return Limit(
                self._child(node),
                self._field(node, "count"),
            )

        if operation == "Sort":
            return Sort(
                self._child(node),
                self._field(node, "keys"),
                self.pages,
            )

        if operation == "Distinct":
            return Distinct(
                self._child(node),
                self.pages,
                mode=node.get("mode", "sort"),
            )

        if operation == "GroupBy":
            return GroupBy(
                self._child(node),
                self._field(node, "keys"),
                self._field(node, "aggregates"),
                self.pages,
                mode=node.get("mode", "sort"),
            )

        if operation in {
            "NestedLoopJoin",
            "SortMergeJoin",
            "GraceHashJoin",
        }:
            if "condition" in node:
                left_key, right_key = self._parse_join_condition(node["condition"])
            else:
                left_key = self._field(node, "left_key")
                right_key = self._field(node, "right_key")

            left, right = self._children(node)

            if "condition" in node:
                left_key, right_key = self._orient_join_keys(
                    left_key,
                    right_key,
                    left,
                    right,
                )

            join_classes = {
                "NestedLoopJoin": NestedLoopJoin,
                "SortMergeJoin": SortMergeJoin,
                "GraceHashJoin": GraceHashJoin,
            }

            return join_classes[operation](
                left,
                right,
                left_key,
                right_key,
                self.pages,
            )

        if operation in {"UnionAll", "Union", "Intersect", "Except"}:
            left, right = self._children(node)

            if operation == "UnionAll":
                return UnionAll(left, right)
            if operation == "Union":
                return Union(left, right, self.pages)
            if operation == "Intersect":
                return Intersect(left, right, self.pages)
            return Except(left, right, self.pages)

        raise ValueError(f"Unsupported physical operator: {operation}")

    def from_json(self, text: str) -> Operator:
        return self.build(json.loads(text))

    def from_file(self, path: str | Path) -> Operator:
        return self.from_json(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _parse_filter_condition(condition: str) -> tuple[str, str, int | str]:
        if not isinstance(condition, str):
            raise TypeError("Filter: 'condition' must be a string")

        expression = parse_condition_text(condition)

        if not isinstance(expression, Comparison):
            raise TypeError("Filter: expected a single comparison condition")

        if not isinstance(expression.left, AttributeReference):
            raise TypeError("Filter: left operand must be a column")

        if not isinstance(expression.right, (NumberLiteral, StringLiteral)):
            raise TypeError("Filter: right operand must be a literal")

        column = (
            f"{expression.left.relation}.{expression.left.name}"
            if expression.left.relation
            else expression.left.name
        )

        return column, expression.operator.value, expression.right.value

    @staticmethod
    def _parse_join_condition(condition: str) -> tuple[str, str]:
        if not isinstance(condition, str):
            raise TypeError("Join: 'condition' must be a string")

        expression = parse_condition_text(condition)

        if not isinstance(expression, Comparison):
            raise TypeError("Join: expected a single comparison condition")

        if expression.operator != ComparisonOperator.EQUAL:
            raise ValueError("Join: only equality conditions are supported")

        if not isinstance(expression.left, AttributeReference):
            raise TypeError("Join: left operand must be a column")

        if not isinstance(expression.right, AttributeReference):
            raise TypeError("Join: right operand must be a column")

        left_key = (
            f"{expression.left.relation}.{expression.left.name}"
            if expression.left.relation
            else expression.left.name
        )
        right_key = (
            f"{expression.right.relation}.{expression.right.name}"
            if expression.right.relation
            else expression.right.name
        )

        return left_key, right_key

    @staticmethod
    def _orient_join_keys(
        left_key: str,
        right_key: str,
        left: Operator,
        right: Operator,
    ) -> tuple[str, str]:
        """Orient qualified join keys to their respective input subtrees."""

        def belongs_to(operator: Operator, column: str) -> bool:
            if "." not in column:
                return False

            relation = column.rsplit(".", 1)[0]

            if isinstance(operator, SeqScan):
                return operator.table_name == relation

            # Nested joins can contain multiple source relations.
            left_child = getattr(operator, "left", None)
            right_child = getattr(operator, "right", None)

            if isinstance(left_child, Operator) and isinstance(right_child, Operator):
                return belongs_to(left_child, column) or belongs_to(right_child, column)

            child = getattr(operator, "child", None)

            if isinstance(child, Operator):
                return belongs_to(child, column)

            return False

        if belongs_to(left, left_key) and belongs_to(right, right_key):
            return left_key, right_key

        if belongs_to(left, right_key) and belongs_to(right, left_key):
            return right_key, left_key

        return left_key, right_key
