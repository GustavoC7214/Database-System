"""Conservative compatibility checks for Module 2 physical joins."""

from dataclasses import dataclass
from typing import Any

from src.optimizer.predicates import (
    ColumnRef,
    ComparisonPredicate,
    parse_predicate,
)

Plan = dict[str, Any]


@dataclass(frozen=True, slots=True)
class JoinCompatibility:
    """Whether a logical join can use Module 2 keyed join operators."""

    supported: bool
    left_key: str | None = None
    right_key: str | None = None
    reason: str = ""


def _available_columns(
    plan: Plan,
    table_columns: dict[str, list[str]],
) -> set[str] | None:
    """Determine columns for a limited set of logical subtrees."""
    operation = plan.get("op")

    if operation == "scan":
        table = plan["table"]
        columns = table_columns.get(table)
        if columns is None:
            return None
        return {f"{table}.{column}" for column in columns}

    if operation == "rename":
        child = _available_columns(plan["child"], table_columns)
        if child is None:
            return None
        alias = plan["to"]
        return {f"{alias}.{column.rsplit('.', 1)[-1]}" for column in child}

    if operation == "project":
        if plan.get("aliases") or plan.get("outputs"):
            return None
        child = _available_columns(plan["child"], table_columns)
        if child is None:
            return None
        projected = set(plan["columns"])
        if not projected <= child:
            return None
        return projected

    if operation in {"select", "sort", "limit", "distinct"}:
        return _available_columns(plan["child"], table_columns)

    if operation in {"join", "cross"}:
        left = _available_columns(plan["left"], table_columns)
        right = _available_columns(plan["right"], table_columns)
        if left is None or right is None:
            return None
        if left & right:
            return None
        return left | right

    return None


def check_join_compatibility(
    plan: Plan,
    *,
    table_columns: dict[str, list[str]],
) -> JoinCompatibility:
    """Validate a simple equijoin and orient its keys.

    This checks join-key structure, not complete physical-plan
    executability. Child operators must be translated separately.
    """
    if plan.get("op") != "join":
        return JoinCompatibility(
            supported=False,
            reason="Expected a logical join operator",
        )

    condition = plan.get("condition")
    if not isinstance(condition, str):
        return JoinCompatibility(
            supported=False,
            reason="Join condition is missing",
        )

    try:
        predicate = parse_predicate(condition)
    except (ValueError, TypeError, SyntaxError):
        return JoinCompatibility(
            supported=False,
            reason="Join condition cannot be parsed",
        )

    if not (
        isinstance(predicate, ComparisonPredicate)
        and predicate.operator == "="
        and isinstance(predicate.left, ColumnRef)
        and isinstance(predicate.right, ColumnRef)
    ):
        return JoinCompatibility(
            supported=False,
            reason="Only simple column equijoins are supported",
        )

    left_columns = _available_columns(
        plan["left"],
        table_columns,
    )
    right_columns = _available_columns(
        plan["right"],
        table_columns,
    )

    if left_columns is None or right_columns is None:
        return JoinCompatibility(
            supported=False,
            reason="Join input columns cannot be determined",
        )

    first = predicate.left.name
    second = predicate.right.name

    if first in left_columns and second in right_columns:
        return JoinCompatibility(
            supported=True,
            left_key=first,
            right_key=second,
        )

    if second in left_columns and first in right_columns:
        return JoinCompatibility(
            supported=True,
            left_key=second,
            right_key=first,
        )

    return JoinCompatibility(
        supported=False,
        reason="Equality columns must belong to opposite join inputs",
    )
