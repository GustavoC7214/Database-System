"""Tests for advanced selection pushdown in Module 4."""

from copy import deepcopy

from src.optimizer.rewrites import rewrite_plan

SCHEMA = {
    "Emp": ["id", "age", "did", "name"],
    "Dept": ["id", "name"],
}


def scan(table="Emp"):
    return {"op": "scan", "table": table}


def select(condition, child):
    return {
        "op": "select",
        "condition": condition,
        "child": child,
    }


def optimize(plan):
    return rewrite_plan(plan, table_columns=SCHEMA)


def test_selection_through_rename():
    plan = select(
        "e.age > 30",
        {"op": "rename", "to": "e", "child": scan()},
    )

    result = optimize(plan)

    assert result["op"] == "rename"
    assert result["child"]["op"] == "select"
    assert result["child"]["condition"] == "Emp.age > 30"


def test_selection_through_rename_with_and():
    plan = select(
        "(e.age > 30 AND e.did = 5)",
        {"op": "rename", "to": "e", "child": scan()},
    )

    result = optimize(plan)

    assert result["op"] == "rename"

    # Both predicates should move below the rename.
    assert result["child"]["op"] == "select"

    # Consecutive selections should be merged into one.
    assert result["child"]["child"]["op"] == "scan"

    # References must be translated back to the original table.
    condition = result["child"]["condition"]

    assert "Emp.age > 30" in condition
    assert "Emp.did = 5" in condition

    # No alias-qualified references should remain below the rename.
    assert "e.age" not in condition
    assert "e.did" not in condition


def test_selection_through_nested_renames():
    plan = select(
        "outer.age > 30",
        {
            "op": "rename",
            "to": "outer",
            "child": {
                "op": "rename",
                "to": "inner",
                "child": scan(),
            },
        },
    )

    result = optimize(plan)

    assert result["op"] == "rename"
    assert result["child"]["op"] == "rename"
    assert result["child"]["child"]["op"] == "select"
    assert result["child"]["child"]["condition"] == "Emp.age > 30"


def test_unknown_rename_column_stays_above():
    plan = select(
        "e.unknown = 5",
        {"op": "rename", "to": "e", "child": scan()},
    )

    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "rename"


def test_grouping_key_filter_pushes():
    plan = select(
        "Emp.did = 5",
        {
            "op": "group_by",
            "keys": ["Emp.did"],
            "aggregates": [["count", "*", "count_star"]],
            "child": scan(),
        },
    )

    result = optimize(plan)

    assert result["op"] == "group_by"
    assert result["child"]["op"] == "select"
    assert result["child"]["condition"] == "Emp.did = 5"


def test_aggregate_filter_stays_above():
    plan = select(
        "count_star > 5",
        {
            "op": "group_by",
            "keys": ["Emp.did"],
            "aggregates": [["count", "*", "count_star"]],
            "child": scan(),
        },
    )

    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "group_by"


def test_mixed_group_filter_splits():
    plan = select(
        "(Emp.did = 5 AND count_star > 2)",
        {
            "op": "group_by",
            "keys": ["Emp.did"],
            "aggregates": [["count", "*", "count_star"]],
            "child": scan(),
        },
    )

    result = optimize(plan)

    assert result["op"] == "select"
    assert result["condition"] == "count_star > 2"
    assert result["child"]["op"] == "group_by"
    assert result["child"]["child"]["op"] == "select"


def test_union_all_filter_pushes_to_both_sides():
    plan = select(
        "Emp.age > 30",
        {
            "op": "union_all",
            "left": scan(),
            "right": scan(),
        },
    )

    result = optimize(plan)

    assert result["op"] == "union_all"
    assert result["left"]["op"] == "select"
    assert result["right"]["op"] == "select"


def test_union_distinct_filter_pushes_to_both_sides():
    plan = select(
        "Emp.age > 30",
        {
            "op": "union",
            "left": scan(),
            "right": scan(),
        },
    )

    result = optimize(plan)

    assert result["op"] == "union"
    assert result["left"]["op"] == "select"
    assert result["right"]["op"] == "select"


def test_union_mismatched_columns_stays_above():
    plan = select(
        "Emp.age > 30",
        {
            "op": "union_all",
            "left": scan(),
            "right": scan("Dept"),
        },
    )

    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "union_all"


def test_consecutive_selections_merge():
    plan = select(
        "Emp.did = 5",
        select("Emp.age > 30", scan()),
    )

    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "scan"
    assert "Emp.age > 30" in result["condition"]
    assert "Emp.did = 5" in result["condition"]


def test_no_mutation():
    plan = select(
        "e.age > 30",
        {"op": "rename", "to": "e", "child": scan()},
    )
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


def test_rewrite_is_deterministic():
    plan = select(
        "(Emp.did = 5 AND Emp.age > 30)",
        scan(),
    )

    assert optimize(plan) == optimize(plan)
