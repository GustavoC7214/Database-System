"""Tests for Phase 3A logical-plan rewriting."""

from copy import deepcopy

from src.optimizer.predicates import parse_predicate
from src.optimizer.rewrites import (
    referenced_columns,
    render_predicate,
    rewrite_plan,
    split_conjunction,
)

SCHEMA = {
    "Emp": ["id", "age", "did", "name"],
    "Dept": ["id", "name"],
}


def scan(table):
    return {"op": "scan", "table": table}


def cross():
    return {
        "op": "cross",
        "left": scan("Emp"),
        "right": scan("Dept"),
    }


def join():
    return {
        "op": "join",
        "condition": "Emp.did = Dept.id",
        "left": scan("Emp"),
        "right": scan("Dept"),
    }


def select(condition, child):
    return {
        "op": "select",
        "condition": condition,
        "child": child,
    }


def optimize(plan, schema=SCHEMA):
    return rewrite_plan(plan, table_columns=schema)


def test_render_comparison():
    predicate = parse_predicate("Emp.age >= 30")
    assert render_predicate(predicate) == "Emp.age >= 30"


def test_render_escaped_string():
    predicate = parse_predicate("Emp.name = 'O''Brien'")
    assert render_predicate(predicate) == "Emp.name = 'O''Brien'"


def test_split_conjunction():
    predicate = parse_predicate("((Emp.age > 30 AND Emp.did = 5) AND Emp.id < 90)")
    parts = split_conjunction(predicate)

    assert len(parts) == 3
    assert [render_predicate(p) for p in parts] == [
        "Emp.age > 30",
        "Emp.did = 5",
        "Emp.id < 90",
    ]


def test_or_is_not_split():
    predicate = parse_predicate("(Emp.age > 30 OR Emp.age < 20)")
    assert len(split_conjunction(predicate)) == 1


def test_referenced_columns():
    predicate = parse_predicate("NOT (Emp.age = 30 OR Dept.id = 5)")
    assert referenced_columns(predicate) == {
        "Emp.age",
        "Dept.id",
    }


def test_push_left_filter_below_join():
    plan = select("Emp.age > 30", join())
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["left"]["op"] == "select"
    assert result["left"]["condition"] == "Emp.age > 30"
    assert result["right"]["op"] == "scan"


def test_push_right_filter_below_join():
    plan = select("Dept.id = 5", join())
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["right"]["op"] == "select"
    assert result["right"]["condition"] == "Dept.id = 5"


def test_push_both_filters():
    plan = select(
        "(Emp.age > 30 AND Dept.id = 5)",
        join(),
    )
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["left"]["op"] == "select"
    assert result["right"]["op"] == "select"


def test_cross_to_join():
    plan = select("Emp.did = Dept.id", cross())
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["condition"] == "Emp.did = Dept.id"


def test_cross_to_join_with_filters():
    plan = select(
        "((Emp.did = Dept.id AND Emp.age > 30) AND Dept.id = 5)",
        cross(),
    )
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["condition"] == "Emp.did = Dept.id"
    assert result["left"]["op"] == "select"
    assert result["right"]["op"] == "select"


def test_multiple_join_equalities():
    plan = select(
        "(Emp.did = Dept.id AND Emp.id = Dept.id)",
        cross(),
    )
    result = optimize(plan)

    assert result["op"] == "join"
    assert "AND" in result["condition"]


def test_cross_range_condition_stays_above():
    plan = select("Emp.age > Dept.id", cross())
    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "cross"


def test_or_across_tables_stays_above():
    plan = select(
        "(Emp.age > 30 OR Dept.id = 5)",
        join(),
    )
    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "join"


def test_ambiguous_unqualified_column_stays_above():
    plan = select("id = 5", join())
    result = optimize(plan)

    assert result["op"] == "select"
    assert result["child"]["op"] == "join"


def test_unqualified_unique_column_pushes():
    plan = select("age > 30", join())
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["left"]["op"] == "select"


def test_missing_schema_prevents_pushdown():
    plan = select("Emp.age > 30", join())
    result = optimize(plan, {})

    assert result["op"] == "select"
    assert result["child"]["op"] == "join"


def test_rename_alias_pushdown():
    plan = select(
        "e.age > 30",
        {
            "op": "join",
            "condition": "e.did = d.id",
            "left": {
                "op": "rename",
                "to": "e",
                "child": scan("Emp"),
            },
            "right": {
                "op": "rename",
                "to": "d",
                "child": scan("Dept"),
            },
        },
    )
    result = optimize(plan)

    assert result["op"] == "join"
    assert result["condition"] == "e.did = d.id"

    # The filter is pushed through the rename.
    assert result["left"]["op"] == "rename"
    assert result["left"]["to"] == "e"

    # The predicate references the original table below the rename.
    assert result["left"]["child"]["op"] == "select"
    assert result["left"]["child"]["condition"] == "Emp.age > 30"
    assert result["left"]["child"]["child"]["op"] == "scan"
    assert result["left"]["child"]["child"]["table"] == "Emp"

    # The right side remains unchanged.
    assert result["right"]["op"] == "rename"
    assert result["right"]["to"] == "d"


def test_original_plan_unchanged():
    plan = select(
        "(Emp.age > 30 AND Dept.id = 5)",
        join(),
    )
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


def test_deterministic_rewrite():
    plan = select(
        "(Emp.did = Dept.id AND Emp.age > 30)",
        cross(),
    )

    assert optimize(plan) == optimize(plan)


def test_nested_join_pushdown():
    plan = select(
        "Emp.age > 30",
        {
            "op": "join",
            "condition": "Emp.did = Dept.id",
            "left": cross(),
            "right": scan("Dept"),
        },
    )
    result = optimize(plan)

    # The predicate belongs inside the left subtree.
    assert result["op"] == "join"
    assert result["left"]["op"] == "cross"
    assert result["left"]["left"]["op"] == "select"
