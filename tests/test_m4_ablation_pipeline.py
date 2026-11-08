"""Tests for configurable Module 4 optimization passes."""

from copy import deepcopy

from src.optimizer.pipeline import optimize_logical_plan

SCHEMAS = {
    "A": ["id", "value"],
    "B": ["id", "amount"],
}


def sample_plan():
    return {
        "op": "project",
        "columns": ["A.id"],
        "child": {
            "op": "select",
            "condition": "A.value > 10",
            "child": {
                "op": "join",
                "condition": "A.id = B.id",
                "left": {"op": "scan", "table": "A"},
                "right": {"op": "scan", "table": "B"},
            },
        },
    }


def contains_operator(plan, operation):
    if plan["op"] == operation:
        return True

    return any(
        contains_operator(plan[key], operation)
        for key in ("child", "left", "right")
        if isinstance(plan.get(key), dict)
    )


def test_default_configuration_matches_explicit_configuration():
    plan = sample_plan()

    default = optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
    )

    explicit = optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
        enable_selection_rewrites=True,
        enable_projection_pushdown=True,
        enable_projection_cleanup=True,
    )

    assert default == explicit


def test_all_passes_disabled_preserves_original_plan():
    plan = sample_plan()

    result = optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
        enable_selection_rewrites=False,
        enable_projection_pushdown=False,
        enable_projection_cleanup=False,
    )

    assert result == plan
    assert result is not plan


def test_disabling_selection_rewrites_keeps_filter_above_join():
    plan = sample_plan()

    result = optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
        enable_selection_rewrites=False,
        enable_projection_pushdown=False,
    )

    assert result["child"]["op"] == "select"
    assert result["child"]["child"]["op"] == "join"


def test_projection_pushdown_can_be_disabled():
    plan = sample_plan()

    result = optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
        enable_selection_rewrites=False,
        enable_projection_pushdown=False,
    )

    assert result == plan


def test_pipeline_does_not_mutate_input():
    plan = sample_plan()
    original = deepcopy(plan)

    optimize_logical_plan(
        plan,
        table_columns=SCHEMAS,
    )

    assert plan == original


def test_projection_pushdown_remains_available():
    result = optimize_logical_plan(
        sample_plan(),
        table_columns=SCHEMAS,
        enable_selection_rewrites=False,
        enable_projection_pushdown=True,
    )

    assert contains_operator(result, "project")
