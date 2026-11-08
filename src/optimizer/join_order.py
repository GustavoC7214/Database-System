"""Deterministic left-deep dynamic-programming join ordering."""

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from src.optimizer.cardinality import (
    estimate_join_rows,
    estimate_pages,
    estimate_rows,
)
from src.optimizer.cost import (
    best_nested_loop_orientation,
    hash_join_cost,
    nested_loop_join_cost,
    sort_merge_join_cost,
)
from src.optimizer.selectivity import equijoin_selectivity
from src.optimizer.statistics import TableStatistics

Plan = dict[str, Any]


@dataclass(frozen=True, slots=True)
class JoinEdge:
    """Equality between columns of two distinct base tables."""

    left_table: str
    left_column: str
    right_table: str
    right_column: str

    def __post_init__(self) -> None:
        if self.left_table == self.right_table:
            raise ValueError("Join edge must connect distinct tables")
        if not self.left_column or not self.right_column:
            raise ValueError("Join columns cannot be empty")

    def connects(self, subset: frozenset[str], table: str) -> bool:
        return (self.left_table in subset and self.right_table == table) or (
            self.right_table in subset and self.left_table == table
        )

    def condition(self) -> str:
        return (
            f"{self.left_table}.{self.left_column} = "
            f"{self.right_table}.{self.right_column}"
        )


@dataclass(frozen=True, slots=True)
class DPEntry:
    """Cheapest known left-deep plan for a table subset."""

    tables: frozenset[str]
    order: tuple[str, ...]
    plan: Plan
    rows: int
    pages: int
    width: float
    cost: int


@dataclass(frozen=True, slots=True)
class JoinOrderResult:
    """Selected plan and the complete retained DP table."""

    best: DPEntry
    entries: tuple[DPEntry, ...]


def _connecting_edges(
    subset: frozenset[str],
    table: str,
    edges: tuple[JoinEdge, ...],
) -> tuple[JoinEdge, ...]:
    """Return all predicates connecting a new table to a subset."""
    return tuple(edge for edge in edges if edge.connects(subset, table))


def _join_output_rows(
    left: DPEntry,
    right: TableStatistics,
    edges: tuple[JoinEdge, ...],
    statistics: dict[str, TableStatistics],
) -> int:
    """Estimate rows using all connecting equality predicates.

    The first predicate uses the existing join cardinality
    estimator. Additional predicates apply selectivity factors.

    Independence is assumed between predicates. Correlated
    columns can therefore cause estimation errors.
    """
    if not edges:
        raise ValueError("Join requires a connecting predicate")

    result = left.rows

    for index, edge in enumerate(edges):
        if edge.left_table in left.tables:
            left_column = _column_statistics(
                statistics,
                edge.left_table,
                edge.left_column,
            )
            right_column = right.columns.get(edge.right_column)
        else:
            left_column = _column_statistics(
                statistics,
                edge.right_table,
                edge.right_column,
            )
            right_column = right.columns.get(edge.left_column)

        if index == 0:
            result = estimate_join_rows(
                left.rows,
                right.n_tuples,
                left_column,
                right_column,
            )
        else:
            result = estimate_rows(
                result,
                equijoin_selectivity(
                    left_column,
                    right_column,
                ),
            )

    return result


def _join_condition(edges: tuple[JoinEdge, ...]) -> str:
    """Preserve every connecting predicate in the logical plan."""
    conditions = [edge.condition() for edge in edges]

    if len(conditions) == 1:
        return conditions[0]

    return "(" + " AND ".join(conditions) + ")"


def _column_statistics(
    statistics: dict[str, TableStatistics],
    table: str,
    column: str,
):
    return statistics[table].columns.get(column)


def _join_algorithm(
    left_pages: int,
    right_pages: int,
    frames: int,
    *,
    allow_swap: bool = True,
) -> tuple[str, int]:
    """Choose the cheapest executable join algorithm.

    A two-table join may reverse its nested-loop inputs.

    For an intermediate left-deep join, the accumulated
    relation must remain the left input, so nested-loop
    costing must use that relation as the outer input.
    """
    if allow_swap:
        orientation, nested = best_nested_loop_orientation(
            left_pages,
            right_pages,
            frames,
        )
    else:
        orientation = "left"
        nested = nested_loop_join_cost(
            left_pages,
            right_pages,
            frames,
        )

    candidates = [
        (nested, 0, f"nested_loop_join:{orientation}"),
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

    cost, _, algorithm = min(candidates)
    return algorithm, cost


def optimize_join_order(
    statistics: dict[str, TableStatistics],
    edges: list[JoinEdge],
    *,
    frames: int = 32,
) -> JoinOrderResult:
    """Find the cheapest connected left-deep equijoin order.

    One plan is retained per table subset. The cost is the
    cumulative analytical I/O score: scan costs plus join
    operator costs. It is not measured physical disk traffic.

    The first version assumes one relevant join predicate
    per expansion. Multiple predicates between the same
    subplans require a later extension.
    """
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("Buffer frames must be an integer")
    if frames < 3:
        raise ValueError("At least three buffer frames are required")

    names = tuple(sorted(statistics))

    if not 2 <= len(names) <= 6:
        raise ValueError("Join ordering requires 2 to 6 tables")

    if not edges:
        raise ValueError("At least one join predicate is required")

    seen_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()

    for edge in edges:
        if edge.left_table not in statistics or edge.right_table not in statistics:
            raise ValueError("Join edge references an unknown table")

        endpoints = tuple(
            sorted(
                (
                    (edge.left_table, edge.left_column),
                    (edge.right_table, edge.right_column),
                )
            )
        )

        if endpoints in seen_edges:
            raise ValueError("Duplicate join predicate")

        seen_edges.add(endpoints)

        for table_name, column_name in endpoints:
            table_stats = statistics[table_name]

            # Empty column statistics mean column-level statistics
            # are unavailable, not necessarily that the column
            # does not exist.
            if table_stats.columns and column_name not in table_stats.columns:
                raise ValueError(f"Unknown join column: {table_name}.{column_name}")

    ordered_edges = tuple(
        sorted(
            edges,
            key=lambda edge: (
                edge.left_table,
                edge.left_column,
                edge.right_table,
                edge.right_column,
            ),
        )
    )

    best: dict[frozenset[str], DPEntry] = {}

    for name in names:
        table = statistics[name]
        subset = frozenset((name,))

        best[subset] = DPEntry(
            tables=subset,
            order=(name,),
            plan={"op": "scan", "table": name},
            rows=table.n_tuples,
            pages=table.n_pages,
            width=table.width,
            cost=table.n_pages,
        )

    for size in range(2, len(names) + 1):
        for members in combinations(names, size):
            subset = frozenset(members)
            candidates: list[DPEntry] = []

            for right_name in members:
                left_subset = subset - {right_name}
                left = best.get(left_subset)

                if left is None:
                    continue

                connecting_edges = _connecting_edges(
                    left_subset,
                    right_name,
                    ordered_edges,
                )

                if not connecting_edges:
                    continue

                right = statistics[right_name]

                algorithm, join_cost = _join_algorithm(
                    left.pages,
                    right.n_pages,
                    frames,
                    allow_swap=len(left.tables) == 1,
                )

                rows = _join_output_rows(
                    left,
                    right,
                    connecting_edges,
                    statistics,
                )

                width = left.width + right.width
                pages = estimate_pages(rows, width)

                # For a two-relation join, the cheaper physical
                # orientation determines the recorded join order.
                #
                # For larger joins, retain the left-deep structure:
                # the right child must remain a base relation.
                order = (*left.order, right_name)
                left_plan = left.plan
                right_plan = {"op": "scan", "table": right_name}

                if len(left.tables) == 1 and algorithm == "nested_loop_join:right":
                    order = (right_name, *left.order)
                    left_plan, right_plan = right_plan, left_plan

                candidates.append(
                    DPEntry(
                        tables=subset,
                        order=order,
                        plan={
                            "op": "join",
                            "condition": _join_condition(connecting_edges),
                            "left": left_plan,
                            "right": right_plan,
                        },
                        rows=rows,
                        pages=pages,
                        width=width,
                        cost=(
                            join_cost
                            if len(left.tables) == 1
                            else left.cost + join_cost
                        ),
                    )
                )

            if candidates:
                best[subset] = min(
                    candidates,
                    key=lambda entry: (entry.cost, entry.order),
                )

    complete = frozenset(names)

    if complete not in best:
        raise ValueError(
            "Join graph is disconnected or cannot form a supported left-deep plan"
        )

    entries = tuple(
        sorted(
            best.values(),
            key=lambda entry: (
                len(entry.tables),
                tuple(sorted(entry.tables)),
            ),
        )
    )

    return JoinOrderResult(
        best=best[complete],
        entries=entries,
    )


def format_dp_table(result: JoinOrderResult) -> str:
    """Format retained DP entries as a deterministic text table."""
    headers = (
        "Subset",
        "Join order",
        "Rows",
        "Pages",
        "I/O cost",
    )

    records = []

    for entry in result.entries:
        records.append(
            (
                "{" + ",".join(sorted(entry.tables)) + "}",
                " -> ".join(entry.order),
                str(entry.rows),
                str(entry.pages),
                str(entry.cost),
            )
        )

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in records))
        for index in range(len(headers))
    ]

    def render(row: tuple[str, ...]) -> str:
        return " | ".join(
            value.ljust(width) for value, width in zip(row, widths, strict=True)
        )

    separator = "-+-".join("-" * width for width in widths)

    return "\n".join(
        [
            render(headers),
            separator,
            *(render(row) for row in records),
        ]
    )


def test_intermediate_join_uses_left_deep_executable_cost():
    """An intermediate join must not cost a reversed nested loop."""

    from src.optimizer.cost import (
        hash_join_cost,
        nested_loop_join_cost,
        sort_merge_join_cost,
    )
    from src.optimizer.join_order import _join_algorithm

    frames = 32
    intermediate_pages = 400
    base_pages = 10

    # Reversing the inputs would be much cheaper, but would
    # put the intermediate result on the right.
    reversed_cost = nested_loop_join_cost(
        base_pages,
        intermediate_pages,
        frames,
    )
    left_deep_cost = nested_loop_join_cost(
        intermediate_pages,
        base_pages,
        frames,
    )

    assert reversed_cost < left_deep_cost

    algorithm, cost = _join_algorithm(
        intermediate_pages,
        base_pages,
        frames,
        allow_swap=False,
    )

    expected = min(
        left_deep_cost,
        hash_join_cost(intermediate_pages, base_pages, frames),
        sort_merge_join_cost(intermediate_pages, base_pages, frames),
    )

    assert cost == expected
    assert algorithm != "nested_loop_join:right"
