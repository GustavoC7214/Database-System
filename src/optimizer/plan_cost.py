"""Recursive page-I/O costing for logical query plans."""

from dataclasses import dataclass
from typing import Any

from src.optimizer.cost import (
    best_nested_loop_orientation,
    hash_join_cost,
    nested_loop_join_cost,
    scan_cost,
    sort_cost,
    sort_merge_join_cost,
)
from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.predicates import (
    ColumnRef,
    ComparisonPredicate,
    parse_predicate,
)
from src.optimizer.statistics import TableStatistics

Plan = dict[str, Any]


@dataclass(frozen=True, slots=True)
class CostedPlan:
    """Cost and estimated output of one plan subtree."""

    operation: str
    algorithm: str
    rows: int
    pages: int
    local_io: int
    total_io: int
    children: tuple["CostedPlan", ...] = ()


def is_equijoin_condition(condition: str) -> bool:
    """Whether a condition is a simple column-to-column equality.

    Complex Boolean conditions are conservatively excluded from
    hash and sort-merge join selection.
    """
    try:
        predicate = parse_predicate(condition)
    except (ValueError, TypeError, SyntaxError):
        return False

    return (
        isinstance(predicate, ComparisonPredicate)
        and predicate.operator == "="
        and isinstance(predicate.left, ColumnRef)
        and isinstance(predicate.right, ColumnRef)
        and predicate.left.name != predicate.right.name
    )


class PhysicalCostEstimator:
    """Estimate recursive I/O and select join algorithms."""

    def __init__(
        self,
        statistics: dict[str, TableStatistics],
        *,
        frames: int = 32,
        table_columns: dict[str, list[str]] | None = None,
    ) -> None:
        if isinstance(frames, bool) or not isinstance(frames, int):
            raise TypeError("Buffer frames must be an integer")
        if frames < 3:
            raise ValueError("At least three buffer frames are required")

        self.statistics = statistics
        self.frames = frames
        self.logical = LogicalPlanEstimator(
            statistics,
            table_columns=table_columns,
        )

    def estimate(self, plan: Plan) -> CostedPlan:
        """Cost a logical tree without modifying it."""
        return self._cost(plan)

    def _cost(self, plan: Plan) -> CostedPlan:
        operation = plan["op"]
        estimate = self.logical.estimate(plan)

        if operation == "scan":
            table = plan["table"]

            # Base-table scans use the actual stored page count.
            # Derived operators continue using estimated output pages.
            statistics = self.logical.statistics.get(table)

            pages = statistics.n_pages if statistics is not None else estimate.pages

            local = scan_cost(pages)

            return CostedPlan(
                operation=operation,
                algorithm="seqscan",
                rows=estimate.rows,
                pages=pages,
                local_io=local,
                total_io=local,
            )

        if operation in {
            "select",
            "project",
            "rename",
            "limit",
            "sort",
            "distinct",
            "group_by",
        }:
            child = self._cost(plan["child"])
            algorithm = operation
            local = 0

            if operation == "select":
                algorithm = "filter"
            elif operation == "sort":
                algorithm = "external_sort"
                local = sort_cost(child.pages, self.frames)
            elif operation == "distinct":
                algorithm = "sort_distinct"
                local = sort_cost(child.pages, self.frames)
            elif operation == "group_by":
                algorithm = "sort_group_by"
                local = sort_cost(child.pages, self.frames)

            return CostedPlan(
                operation=operation,
                algorithm=algorithm,
                rows=estimate.rows,
                pages=estimate.pages,
                local_io=local,
                total_io=child.total_io + local,
                children=(child,),
            )

        if operation in {"join", "cross"}:
            left = self._cost(plan["left"])
            right = self._cost(plan["right"])

            both_scans = (
                plan["left"].get("op") == "scan" and plan["right"].get("op") == "scan"
            )

            if both_scans:
                orientation, nested_cost = best_nested_loop_orientation(
                    left.pages,
                    right.pages,
                    self.frames,
                )
            else:
                orientation = "left"
                nested_cost = nested_loop_join_cost(
                    left.pages,
                    right.pages,
                    self.frames,
                )

            algorithm = f"nested_loop_join:{orientation}"
            local = nested_cost

            # Hash and sort-merge joins require a supported equality
            # predicate. A cross join has no equality predicate.
            condition = plan.get("condition")
            eligible = (
                operation == "join"
                and isinstance(condition, str)
                and is_equijoin_condition(condition)
            )

            if eligible:
                candidates = [
                    (nested_cost, 0, algorithm),
                    (
                        hash_join_cost(
                            left.pages,
                            right.pages,
                            self.frames,
                        ),
                        1,
                        "hash_join",
                    ),
                    (
                        sort_merge_join_cost(
                            left.pages,
                            right.pages,
                            self.frames,
                        ),
                        2,
                        "sort_merge_join",
                    ),
                ]

                local, _, algorithm = min(candidates)

            return CostedPlan(
                operation=operation,
                algorithm=algorithm,
                rows=estimate.rows,
                pages=estimate.pages,
                local_io=local,
                total_io=left.total_io + right.total_io + local,
                children=(left, right),
            )

        if operation in {
            "union",
            "union_all",
            "intersect",
            "except",
        }:
            left = self._cost(plan["left"])
            right = self._cost(plan["right"])

            if operation == "union_all":
                local = 0
                algorithm = "union_all"
            else:
                # Approximate duplicate elimination / set matching
                # using an external sort of the combined inputs.
                local = sort_cost(
                    left.pages + right.pages,
                    self.frames,
                )
                algorithm = f"sort_{operation}"

            return CostedPlan(
                operation=operation,
                algorithm=algorithm,
                rows=estimate.rows,
                pages=estimate.pages,
                local_io=local,
                total_io=left.total_io + right.total_io + local,
                children=(left, right),
            )

        raise ValueError(f"Unsupported logical operation: {operation}")
