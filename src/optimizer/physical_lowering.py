"""Conservative lowering of SQL logical plans to Module 2 physical plans."""

from typing import Any

from src.optimizer.cost import (
    best_nested_loop_orientation,
    hash_join_cost,
    nested_loop_join_cost,
    sort_merge_join_cost,
)
from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.predicates import (
    BooleanPredicate,
    ColumnRef,
    ComparisonPredicate,
    LiteralValue,
    parse_predicate,
)
from src.optimizer.statistics import TableStatistics
from src.optimizer.statistics_fallback import complete_statistics

Plan = dict[str, Any]


class UnsupportedPhysicalPlan(ValueError):
    """A logical plan cannot safely use the current physical operators."""


def lower_physical_plan(
    plan: Plan,
    statistics: dict[str, TableStatistics],
    *,
    table_columns: dict[str, list[str]],
    frames: int = 32,
    join_algorithm: str | None = None,
    preserve_join_order: bool = False,
) -> Plan:
    """Translate a supported SQL logical plan to Module 2 JSON.

    This is deliberately a restricted subset. In particular, aliases,
    cross joins, compound predicates, and grouping are not lowered.
    """
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("Buffer frames must be an integer")
    if frames < 3:
        raise ValueError("At least three buffer frames are required")

    allowed_algorithms = {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    if join_algorithm is not None and join_algorithm not in allowed_algorithms:
        raise ValueError(f"Unsupported join algorithm: {join_algorithm!r}")

    def referenced_tables(node: Plan) -> set[str]:
        tables: set[str] = set()

        if node.get("op") == "scan":
            table = node.get("table")
            if isinstance(table, str):
                tables.add(table)

        for key in ("child", "left", "right"):
            child = node.get(key)
            if isinstance(child, dict):
                tables.update(referenced_tables(child))

        return tables

    tables = referenced_tables(plan)

    unknown = sorted(tables - table_columns.keys())
    if unknown:
        raise UnsupportedPhysicalPlan("Unknown table schema: " + ", ".join(unknown))

    statistics = complete_statistics(tables, statistics)

    estimator = LogicalPlanEstimator(
        statistics,
        table_columns=table_columns,
    )

    def subtree_tables(node: Plan) -> set[str]:
        operation = node.get("op")

        if operation == "scan":
            return {node["table"]}

        if operation == "join":
            return subtree_tables(node["left"]) | subtree_tables(node["right"])

        if operation in {"select", "project", "limit", "sort", "distinct"}:
            return subtree_tables(node["child"])

        raise UnsupportedPhysicalPlan(
            f"Cannot determine table ownership for {operation!r}"
        )

    def subtree_pages(node: Plan) -> int:
        """Estimate intermediate pages using logical cardinality estimates.

        Base-table scans use the actual stored page count from ANALYZE.
        Intermediate operators use the logical estimator's output pages.
        """
        operation = node.get("op")

        if operation == "scan":
            table = node["table"]

            if table not in statistics:
                raise UnsupportedPhysicalPlan(f"Missing table statistics: {table}")

            return statistics[table].n_pages

        if operation in {"select", "project", "limit", "join", "sort", "distinct"}:
            for table in subtree_tables(node):
                if table not in statistics:
                    raise UnsupportedPhysicalPlan(f"Missing table statistics: {table}")

            return estimator.estimate(node).pages

        raise UnsupportedPhysicalPlan(f"Cannot estimate pages for {operation!r}")

    def validate_column(column: str, tables: set[str]) -> None:
        if column.count(".") != 1:
            raise UnsupportedPhysicalPlan(f"Expected qualified column: {column}")

        table, name = column.split(".")

        if table not in tables or name not in table_columns.get(table, []):
            raise UnsupportedPhysicalPlan(f"Column is unavailable: {column}")

    def lower(node: Plan) -> Plan:
        operation = node.get("op")

        if operation == "scan":
            table = node.get("table")

            if table not in table_columns:
                raise UnsupportedPhysicalPlan(f"Unknown table schema: {table}")

            return {"op": "seqscan", "table": table}

        if operation == "project":
            child = node["child"]
            tables = subtree_tables(child)
            columns = node.get("columns")

            if not isinstance(columns, list) or not all(
                isinstance(column, str) for column in columns
            ):
                raise UnsupportedPhysicalPlan(
                    "Projection requires a list of column names"
                )

            if "aliases" in node or "outputs" in node:
                raise UnsupportedPhysicalPlan("Projection aliases are not supported")

            for column in columns:
                validate_column(column, tables)

            return {
                "op": "project",
                "columns": list(columns),
                "child": lower(child),
            }

        if operation == "sort":
            keys = node.get("keys")

            if not isinstance(keys, list):
                raise UnsupportedPhysicalPlan("SORT requires a list of keys")

            for key in keys:
                if not (
                    isinstance(key, (list, tuple))
                    and len(key) == 2
                    and isinstance(key[0], str)
                    and isinstance(key[1], str)
                    and key[1].upper() in {"ASC", "DESC"}
                ):
                    raise UnsupportedPhysicalPlan(f"Invalid sort key: {key!r}")

            return {
                "op": "sort",
                "keys": [[column, direction.upper()] for column, direction in keys],
                "child": lower(node["child"]),
            }

        if operation == "distinct":
            return {
                "op": "distinct",
                "child": lower(node["child"]),
            }

        if operation == "limit":
            count = node.get("count")

            if isinstance(count, bool) or not isinstance(count, int):
                raise UnsupportedPhysicalPlan("LIMIT requires an integer count")
            if count < 0:
                raise UnsupportedPhysicalPlan("LIMIT cannot be negative")

            return {
                "op": "limit",
                "count": count,
                "child": lower(node["child"]),
            }

        if operation == "select":
            condition = node.get("condition")

            try:
                predicate = parse_predicate(condition)
            except (TypeError, ValueError, SyntaxError) as exc:
                raise UnsupportedPhysicalPlan("Unsupported filter expression") from exc

            child_plan = lower(node["child"])
            available_tables = subtree_tables(node["child"])

            def lower_filter(predicate, child):
                """Lower AND predicates without moving their location."""
                if isinstance(predicate, BooleanPredicate):
                    if predicate.operator != "AND":
                        raise UnsupportedPhysicalPlan(
                            "Only AND compound filters are supported"
                        )

                    left_plan = lower_filter(predicate.left, child)
                    return lower_filter(predicate.right, left_plan)

                if not (
                    isinstance(predicate, ComparisonPredicate)
                    and isinstance(predicate.left, ColumnRef)
                    and isinstance(predicate.right, LiteralValue)
                ):
                    raise UnsupportedPhysicalPlan(
                        "Physical filters require column-to-literal comparisons"
                    )

                validate_column(predicate.left.name, available_tables)

                return {
                    "op": "filter",
                    "column": predicate.left.name,
                    "comparison": predicate.operator,
                    "value": predicate.right.value,
                    "child": child,
                }

            return lower_filter(predicate, child_plan)

        if operation == "join":
            condition = node.get("condition")

            try:
                predicate = parse_predicate(condition)
            except (TypeError, ValueError, SyntaxError) as exc:
                raise UnsupportedPhysicalPlan("Unsupported join expression") from exc

            if not (
                isinstance(predicate, ComparisonPredicate)
                and predicate.operator == "="
                and isinstance(predicate.left, ColumnRef)
                and isinstance(predicate.right, ColumnRef)
            ):
                raise UnsupportedPhysicalPlan(
                    "Physical joins require one equality predicate"
                )

            left_tables = subtree_tables(node["left"])
            right_tables = subtree_tables(node["right"])

            if left_tables & right_tables:
                raise UnsupportedPhysicalPlan(
                    "Repeated table references require alias support"
                )

            first = predicate.left.name
            second = predicate.right.name

            if (
                first.split(".")[0] in left_tables
                and second.split(".")[0] in right_tables
            ):
                left_key, right_key = first, second
            elif (
                second.split(".")[0] in left_tables
                and first.split(".")[0] in right_tables
            ):
                left_key, right_key = second, first
            else:
                raise UnsupportedPhysicalPlan(
                    "Join keys must belong to opposite inputs"
                )

            validate_column(left_key, left_tables)
            validate_column(right_key, right_tables)

            left_pages = subtree_pages(node["left"])
            right_pages = subtree_pages(node["right"])

            # A join with an intermediate left input must retain
            # its left-deep structure.
            both_scans = (
                node["left"].get("op") == "scan" and node["right"].get("op") == "scan"
            )

            if both_scans and not preserve_join_order:
                orientation, nested_cost = best_nested_loop_orientation(
                    left_pages,
                    right_pages,
                    frames,
                )
            else:
                orientation = "left"
                nested_cost = nested_loop_join_cost(
                    left_pages,
                    right_pages,
                    frames,
                )

            candidates = [
                (nested_cost, 0, "nested_loop_join"),
                (
                    hash_join_cost(left_pages, right_pages, frames),
                    1,
                    "hash_join",
                ),
                (
                    sort_merge_join_cost(left_pages, right_pages, frames),
                    2,
                    "sort_merge_join",
                ),
            ]

            if join_algorithm is None:
                _, _, algorithm = min(candidates)
            else:
                algorithm = join_algorithm

            left_child = node["left"]
            right_child = node["right"]

            # Block nested-loop joins are asymmetric: the smaller
            # outer relation may require fewer repeated inner scans.
            #
            # Swap inputs and join keys only when the selected
            # nested-loop orientation requires it.
            if (
                not preserve_join_order
                and algorithm == "nested_loop_join"
                and orientation == "right"
                and node["left"].get("op") == "scan"
                and node["right"].get("op") == "scan"
            ):
                left_child, right_child = right_child, left_child
                left_key, right_key = right_key, left_key

            return {
                "op": algorithm,
                "left_key": left_key,
                "right_key": right_key,
                "left": lower(left_child),
                "right": lower(right_child),
            }

        raise UnsupportedPhysicalPlan(f"Unsupported logical operator: {operation!r}")

    return lower(plan)
