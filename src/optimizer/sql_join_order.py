"""Conservative SQL logical-plan integration for join ordering."""

from copy import deepcopy
from typing import Any

from src.optimizer.join_order import JoinEdge, optimize_join_order
from src.optimizer.predicates import (
    ColumnRef,
    ComparisonPredicate,
    parse_predicate,
)
from src.optimizer.statistics import TableStatistics

Plan = dict[str, Any]


def _extract_join_tree(
    plan: Plan,
    table_columns: dict[str, list[str]],
) -> tuple[set[str], list[JoinEdge]] | None:
    """Extract an unaliased, inner-equijoin-only tree.

    Returns None when reordering cannot be proven safe.
    """
    operation = plan.get("op")

    if operation == "scan":
        table = plan.get("table")

        if not isinstance(table, str):
            return None
        if table not in table_columns:
            return None

        return {table}, []

    if operation != "join":
        return None

    left = _extract_join_tree(plan["left"], table_columns)
    right = _extract_join_tree(plan["right"], table_columns)

    if left is None or right is None:
        return None

    left_tables, left_edges = left
    right_tables, right_edges = right

    if left_tables & right_tables:
        return None

    condition = plan.get("condition")
    if not isinstance(condition, str):
        return None

    try:
        predicate = parse_predicate(condition)
    except (ValueError, TypeError, SyntaxError):
        return None

    if not (
        isinstance(predicate, ComparisonPredicate)
        and predicate.operator == "="
        and isinstance(predicate.left, ColumnRef)
        and isinstance(predicate.right, ColumnRef)
    ):
        return None

    first = predicate.left.name
    second = predicate.right.name

    if first.count(".") != 1 or second.count(".") != 1:
        return None

    first_table, first_column = first.split(".")
    second_table, second_column = second.split(".")

    # Require opposite sides of this particular join.
    if first_table in left_tables and second_table in right_tables:
        pass
    elif second_table in left_tables and first_table in right_tables:
        (
            first_table,
            second_table,
            first_column,
            second_column,
        ) = (
            second_table,
            first_table,
            second_column,
            first_column,
        )
    else:
        return None

    if (
        first_column not in table_columns[first_table]
        or second_column not in table_columns[second_table]
    ):
        return None

    edge = JoinEdge(
        first_table,
        first_column,
        second_table,
        second_column,
    )

    return (
        left_tables | right_tables,
        [*left_edges, *right_edges, edge],
    )


def _optimize_tree(
    plan: Plan,
    statistics: dict[str, TableStatistics],
    table_columns: dict[str, list[str]],
    frames: int,
) -> Plan | None:
    extracted = _extract_join_tree(plan, table_columns)

    if extracted is None:
        return None

    tables, edges = extracted

    if not 2 <= len(tables) <= 6:
        return None

    if not tables <= statistics.keys():
        return None

    try:
        result = optimize_join_order(
            {table: statistics[table] for table in sorted(tables)},
            edges,
            frames=frames,
        )
    except ValueError:
        # Invalid or unsupported join graphs retain the original plan.
        return None

    return result.best.plan


def optimize_sql_join_order(
    plan: Plan,
    statistics: dict[str, TableStatistics],
    *,
    table_columns: dict[str, list[str]],
    frames: int = 32,
) -> Plan:
    """Reorder eligible inner-join subtrees in a compiled SQL plan.

    The input is never mutated. Unsupported subtrees retain their
    original structure. This does not execute or compile SQL text.
    """
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("Buffer frames must be an integer")
    if frames < 3:
        raise ValueError("At least three buffer frames are required")

    def visit(node: Plan) -> Plan:
        result = dict(node)

        if "child" in result and isinstance(result["child"], dict):
            result["child"] = visit(result["child"])

        if "left" in result and isinstance(result["left"], dict):
            result["left"] = visit(result["left"])

        if "right" in result and isinstance(result["right"], dict):
            result["right"] = visit(result["right"])

        if result.get("op") == "join":
            optimized = _optimize_tree(
                result,
                statistics,
                table_columns,
                frames,
            )
            if optimized is not None:
                return optimized

        return result

    return visit(deepcopy(plan))
