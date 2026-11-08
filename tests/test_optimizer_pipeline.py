"""Tests for the integrated logical optimizer pipeline."""

from copy import deepcopy

from src.optimizer.pipeline import (
    cleanup_projections,
    optimize_logical_plan,
)

SCHEMA = {
    "Emp": ["id", "age", "did", "name"],
    "Dept": ["id", "name", "location"],
}


def scan(table="Emp"):
    return {"op": "scan", "table": table}


def project(columns, child):
    return {
        "op": "project",
        "columns": columns,
        "child": child,
    }


def select(condition, child):
    return {
        "op": "select",
        "condition": condition,
        "child": child,
    }


def cross():
    return {
        "op": "cross",
        "left": scan(),
        "right": scan("Dept"),
    }


def optimize(plan):
    return optimize_logical_plan(
        plan,
        table_columns=SCHEMA,
    )


def test_redundant_adjacent_projection_removed():
    plan = project(
        ["Emp.name"],
        project(["Emp.name"], scan()),
    )

    result = cleanup_projections(plan)

    assert result == project(["Emp.name"], scan())


def test_different_projections_preserved():
    plan = project(
        ["Emp.name"],
        project(["Emp.id", "Emp.name"], scan()),
    )

    result = cleanup_projections(plan)

    assert result == plan


def test_projection_order_matters():
    plan = project(
        ["Emp.name", "Emp.id"],
        project(["Emp.id", "Emp.name"], scan()),
    )

    assert cleanup_projections(plan) == plan


def test_aliased_projection_preserved():
    inner = {
        "op": "project",
        "columns": ["Emp.name"],
        "aliases": {"employee": "Emp.name"},
        "outputs": ["employee"],
        "child": scan(),
    }
    plan = project(["employee"], inner)

    assert cleanup_projections(plan) == plan


def test_redundant_projection_in_join_branch():
    plan = {
        "op": "join",
        "condition": "Emp.did = Dept.id",
        "left": project(
            ["Emp.did", "Emp.name"],
            project(
                ["Emp.did", "Emp.name"],
                scan(),
            ),
        ),
        "right": scan("Dept"),
    }

    result = cleanup_projections(plan)

    assert result["left"]["child"]["op"] == "scan"


def test_selection_and_projection_integration():
    plan = project(
        ["Emp.name"],
        select("Emp.age > 30", scan()),
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["child"]["op"] == "select"
    assert result["child"]["child"]["op"] == "project"
    assert result["child"]["child"]["columns"] == [
        "Emp.age",
        "Emp.name",
    ]


def test_cross_to_join_and_projection_pushdown():
    plan = project(
        ["Emp.name"],
        select(
            "(Emp.did = Dept.id AND Emp.age > 30)",
            cross(),
        ),
    )

    result = optimize(plan)

    assert result["op"] == "project"

    joined = result["child"]
    assert joined["op"] == "join"
    assert joined["condition"] == "Emp.did = Dept.id"

    assert joined["left"]["op"] == "project"
    assert joined["right"]["op"] == "project"

    assert joined["left"]["columns"] == [
        "Emp.did",
        "Emp.name",
    ]
    assert joined["right"]["columns"] == ["Dept.id"]

    filtered = joined["left"]["child"]
    assert filtered["op"] == "select"
    assert filtered["condition"] == "Emp.age > 30"
    assert filtered["child"]["op"] == "project"
    assert filtered["child"]["columns"] == [
        "Emp.age",
        "Emp.did",
        "Emp.name",
    ]


def test_no_root_projection_preserves_all_outputs():
    plan = select("Emp.age > 30", cross())

    result = optimize(plan)

    assert result["op"] == "cross"
    assert result["left"]["op"] == "select"
    assert result["right"]["op"] == "scan"


def test_missing_schema_is_conservative():
    plan = project(
        ["Emp.name"],
        select("Emp.age > 30", scan()),
    )

    result = optimize_logical_plan(
        plan,
        table_columns={},
    )

    assert result == plan


def test_original_plan_unchanged():
    plan = project(
        ["Emp.name"],
        select(
            "Emp.did = Dept.id",
            cross(),
        ),
    )
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


def test_pipeline_deterministic():
    plan = project(
        ["Emp.name"],
        select(
            "(Emp.did = Dept.id AND Emp.age > 30)",
            cross(),
        ),
    )

    assert optimize(plan) == optimize(plan)


def test_pipeline_idempotent():
    plan = project(
        ["Emp.name"],
        select(
            "(Emp.did = Dept.id AND Emp.age > 30)",
            cross(),
        ),
    )

    once = optimize(plan)
    twice = optimize(once)

    assert once == twice


def test_cleanup_idempotent():
    plan = project(
        ["Emp.name"],
        project(
            ["Emp.name"],
            project(["Emp.name"], scan()),
        ),
    )

    once = cleanup_projections(plan)
    twice = cleanup_projections(once)

    assert once == twice


def test_nested_redundant_projections():
    plan = project(
        ["Emp.name"],
        project(
            ["Emp.name"],
            project(["Emp.name"], scan()),
        ),
    )

    result = cleanup_projections(plan)

    assert result == project(["Emp.name"], scan())


def test_rename_with_projection_pipeline():
    plan = project(
        ["e.name"],
        select(
            "e.age > 30",
            {
                "op": "rename",
                "to": "e",
                "child": scan(),
            },
        ),
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["child"]["op"] == "rename"
    assert result["child"]["child"]["op"] == "select"
    assert result["child"]["child"]["condition"] == "Emp.age > 30"
