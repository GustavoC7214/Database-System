"""Cardinality estimates for Module 3 logical-plan trees.

The estimator never mutates its input plan. It propagates source-table
cardinalities alongside column statistics so histogram selectivities
remain correctly normalized after joins and other operations.
"""

import math
from dataclasses import dataclass
from typing import Any

from src.optimizer.cardinality import estimate_pages, estimate_rows
from src.optimizer.predicates import (
    BooleanPredicate,
    ColumnRef,
    LiteralValue,
    NotPredicate,
    Predicate,
    parse_predicate,
)
from src.optimizer.selectivity import (
    and_selectivity,
    comparison_selectivity,
    equijoin_selectivity,
    not_selectivity,
    or_selectivity,
)
from src.optimizer.statistics import ColumnStatistics, TableStatistics

Plan = dict[str, Any]

DEFAULT_TABLE_ROWS = 1000
DEFAULT_ROW_WIDTH = 16.0
DEFAULT_DISTINCT_FRACTION = 0.5
DEFAULT_GROUP_FRACTION = 0.1


@dataclass(frozen=True, slots=True)
class ColumnEstimate:
    """Column statistics and their original source cardinality."""

    statistics: ColumnStatistics | None
    source_rows: int
    width: float


@dataclass(slots=True)
class NodeEstimate:
    """Internal estimate for a logical operator."""

    plan: Plan
    rows: int
    pages: int
    width: float
    columns: dict[str, ColumnEstimate]


def _annotate(
    plan: Plan,
    rows: int,
    width: float,
    columns: dict[str, ColumnEstimate],
) -> NodeEstimate:
    pages = estimate_pages(rows, width)
    annotated = dict(plan)
    annotated["est_rows"] = rows
    annotated["est_pages"] = pages
    annotated["est_width"] = round(width, 4)
    return NodeEstimate(annotated, rows, pages, width, columns)


def _resolve(
    name: str,
    columns: dict[str, ColumnEstimate],
) -> ColumnEstimate | None:
    if name in columns:
        return columns[name]

    if "." in name:
        return None

    matches = [
        value for key, value in columns.items() if key.rsplit(".", 1)[-1] == name
    ]
    return matches[0] if len(matches) == 1 else None


def _predicate_selectivity(
    predicate: Predicate,
    columns: dict[str, ColumnEstimate],
) -> float:
    if isinstance(predicate, NotPredicate):
        return not_selectivity(_predicate_selectivity(predicate.operand, columns))

    if isinstance(predicate, BooleanPredicate):
        left = _predicate_selectivity(predicate.left, columns)
        right = _predicate_selectivity(predicate.right, columns)
        if predicate.operator == "AND":
            return and_selectivity(left, right)
        return or_selectivity(left, right)

    left = predicate.left
    right = predicate.right
    operator = predicate.operator

    if isinstance(left, ColumnRef) and isinstance(right, LiteralValue):
        info = _resolve(left.name, columns)
        return comparison_selectivity(
            info.statistics if info else None,
            operator,
            right.value,
            n_tuples=info.source_rows if info else None,
        )

    if isinstance(left, LiteralValue) and isinstance(right, ColumnRef):
        reverse = {
            "=": "=",
            "==": "==",
            "!=": "!=",
            "<>": "<>",
            "<": ">",
            "<=": ">=",
            ">": "<",
            ">=": "<=",
        }
        info = _resolve(right.name, columns)
        return comparison_selectivity(
            info.statistics if info else None,
            reverse[operator],
            left.value,
            n_tuples=info.source_rows if info else None,
        )

    if isinstance(left, ColumnRef) and isinstance(right, ColumnRef):
        if left.name == right.name:
            return float(operator in {"=", "==", "<=", ">="})

        left_info = _resolve(left.name, columns)
        right_info = _resolve(right.name, columns)
        left_stats = left_info.statistics if left_info else None
        right_stats = right_info.statistics if right_info else None

        if operator in {"=", "=="}:
            return equijoin_selectivity(left_stats, right_stats)
        if operator in {"!=", "<>"}:
            return not_selectivity(equijoin_selectivity(left_stats, right_stats))
        return 0.1

    # Reuse the existing predicate estimator for literal-only comparisons.
    from src.optimizer.predicates import estimate_predicate

    return estimate_predicate(predicate, {})


def _estimate_groups(
    rows: int,
    keys: list[str],
    columns: dict[str, ColumnEstimate],
) -> int:
    if not keys:
        # Global aggregation produces one result, even on empty input.
        return 1

    if rows == 0:
        return 0

    distinct_product = 1
    for key in keys:
        info = _resolve(key, columns)
        if info is None or info.statistics is None:
            return max(1, math.ceil(rows * DEFAULT_GROUP_FRACTION))
        distinct_product *= max(1, info.statistics.ndv)

    return min(rows, distinct_product)


class LogicalPlanEstimator:
    """Estimate cardinality, pages, and width for logical JSON plans."""

    def __init__(
        self,
        statistics: dict[str, TableStatistics],
        *,
        table_columns: dict[str, list[str]] | None = None,
    ) -> None:
        self.statistics = statistics
        self.table_columns = table_columns or {}

    def estimate(self, plan: Plan) -> NodeEstimate:
        """Return an annotated copy and the root's estimated properties."""
        return self._visit(plan)

    def annotate(self, plan: Plan) -> Plan:
        """Return only the annotated logical-plan dictionary."""
        return self.estimate(plan).plan

    def _scan(self, plan: Plan) -> NodeEstimate:
        table = plan["table"]
        stats = self.statistics.get(table)

        if stats is None:
            rows = DEFAULT_TABLE_ROWS
            width = DEFAULT_ROW_WIDTH
            names = self.table_columns.get(table, [])
            column_stats: dict[str, ColumnStatistics] = {}
        else:
            rows = stats.n_tuples
            width = stats.width
            names = self.table_columns.get(table, list(stats.columns))
            column_stats = stats.columns

        column_width = width / len(names) if names else width
        columns = {
            f"{table}.{name}": ColumnEstimate(
                column_stats.get(name),
                rows,
                column_width,
            )
            for name in names
        }
        return _annotate(plan, rows, width, columns)

    def _unary(self, plan: Plan) -> NodeEstimate:
        child = self._visit(plan["child"])
        op = plan["op"]
        output = dict(plan)
        output["child"] = child.plan

        rows = child.rows
        width = child.width
        columns = dict(child.columns)

        if op == "select":
            selectivity = _predicate_selectivity(
                parse_predicate(plan["condition"]),
                columns,
            )
            rows = estimate_rows(rows, selectivity)

        elif op == "rename":
            alias = plan["to"]
            renamed: dict[str, ColumnEstimate] = {}
            for name, info in columns.items():
                renamed[f"{alias}.{name.rsplit('.', 1)[-1]}"] = info
            columns = renamed

        elif op == "project":
            selected = plan["columns"]
            outputs = plan.get("outputs", selected)
            projected: dict[str, ColumnEstimate] = {}
            projected_width = 0.0

            for source, target in zip(selected, outputs, strict=True):
                info = _resolve(source, columns)
                if info is None:
                    info = ColumnEstimate(None, rows, DEFAULT_ROW_WIDTH)
                projected[target] = info
                projected_width += info.width

            columns = projected
            width = projected_width

        elif op == "group_by":
            keys = plan.get("keys", [])
            rows = _estimate_groups(rows, keys, columns)
            grouped: dict[str, ColumnEstimate] = {}
            width = 0.0

            for key in keys:
                info = _resolve(key, columns)
                if info is None:
                    info = ColumnEstimate(None, child.rows, DEFAULT_ROW_WIDTH)
                grouped[key] = info
                width += info.width

            for function, argument, output_name in plan.get("aggregates", []):
                del function, argument
                grouped[output_name] = ColumnEstimate(None, rows, 8.0)
                width += 8.0

            columns = grouped

        elif op == "distinct":
            if rows > 0:
                known = [
                    info.statistics.ndv
                    for info in columns.values()
                    if info.statistics is not None
                ]
                if known and len(known) == len(columns):
                    distinct_count = math.prod(known)
                    rows = min(rows, max(1, distinct_count))
                else:
                    rows = max(1, math.ceil(rows * DEFAULT_DISTINCT_FRACTION))

        elif op == "limit":
            rows = min(rows, max(0, plan["count"]))

        elif op != "sort":
            raise ValueError(f"Unsupported unary logical operator: {op}")

        return _annotate(output, rows, width, columns)

    def _binary(self, plan: Plan) -> NodeEstimate:
        left = self._visit(plan["left"])
        right = self._visit(plan["right"])
        op = plan["op"]

        output = dict(plan)
        output["left"] = left.plan
        output["right"] = right.plan

        columns = {**left.columns, **right.columns}
        width = left.width + right.width

        if op == "cross":
            rows = left.rows * right.rows

        elif op == "join":
            selectivity = _predicate_selectivity(
                parse_predicate(plan["condition"]),
                columns,
            )
            rows = estimate_rows(left.rows * right.rows, selectivity)

        elif op == "union_all":
            rows = left.rows + right.rows
            width = max(left.width, right.width)
            columns = dict(left.columns)

        elif op == "union":
            rows = max(left.rows, right.rows)
            width = max(left.width, right.width)
            columns = dict(left.columns)

        elif op == "intersect":
            rows = min(left.rows, right.rows) // 2
            width = left.width
            columns = dict(left.columns)

        elif op == "except":
            rows = max(0, left.rows - right.rows // 2)
            width = left.width
            columns = dict(left.columns)

        else:
            raise ValueError(f"Unsupported binary logical operator: {op}")

        return _annotate(output, rows, width, columns)

    def _visit(self, plan: Plan) -> NodeEstimate:
        op = plan.get("op")

        if op == "scan":
            return self._scan(plan)

        if op in {
            "select",
            "project",
            "rename",
            "group_by",
            "sort",
            "distinct",
            "limit",
        }:
            return self._unary(plan)

        if op in {
            "cross",
            "join",
            "union",
            "union_all",
            "intersect",
            "except",
        }:
            return self._binary(plan)

        raise ValueError(f"Unsupported logical operator: {op!r}")
