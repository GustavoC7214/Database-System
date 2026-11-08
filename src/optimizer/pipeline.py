"""Logical rewrite pipeline for Module 4."""

from copy import deepcopy
from typing import Any

from src.optimizer.projection_pushdown import push_projections
from src.optimizer.rewrites import rewrite_plan

Plan = dict[str, Any]


def _plain_projection(plan: Plan) -> bool:
    """Whether a projection has no output renaming."""
    return (
        plan.get("op") == "project"
        and not plan.get("aliases")
        and not plan.get("outputs")
    )


def _cleanup(plan: Plan) -> Plan:
    """Remove redundant adjacent projections recursively."""
    result = dict(plan)

    if "child" in result:
        result["child"] = _cleanup(result["child"])

    if "left" in result and "right" in result:
        result["left"] = _cleanup(result["left"])
        result["right"] = _cleanup(result["right"])

    if not _plain_projection(result):
        return result

    child = result.get("child")
    if not isinstance(child, dict):
        return result

    if not _plain_projection(child):
        return result

    # Equal ordered column lists make the inner projection
    # redundant. Do not reorder columns or alter aliases.
    if result["columns"] == child["columns"]:
        result["child"] = child["child"]

    return result


def cleanup_projections(plan: Plan) -> Plan:
    """Remove safe redundant projections without mutation."""
    return _cleanup(deepcopy(plan))


def optimize_logical_plan(
    plan: Plan,
    *,
    table_columns: dict[str, list[str]] | None = None,
    enable_selection_rewrites: bool = True,
    enable_projection_pushdown: bool = True,
    enable_projection_cleanup: bool = True,
) -> Plan:
    """Apply configurable Module 4 logical rewrite passes.

    Selection rewrites also include conjunct splitting and
    cross-product-to-join conversion.

    The original plan is never modified.
    """
    schemas = table_columns or {}

    current = deepcopy(plan)

    if enable_selection_rewrites:
        current = rewrite_plan(
            current,
            table_columns=schemas,
        )

    if enable_projection_pushdown:
        current = push_projections(
            current,
            table_columns=schemas,
        )

    if enable_projection_cleanup:
        current = cleanup_projections(current)

    return current
