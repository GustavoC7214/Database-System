"""Tests for conservative projection pushdown."""

from copy import deepcopy

from src.optimizer.projection_pushdown import push_projections

SCHEMA = {
    "Emp": ["id", "age", "did", "name"],
    "Dept": ["id", "name", "location"],
}


def scan(table="Emp"):
    return {"op": "scan", "table": table}


def project(columns, child):
    return {"op": "project", "columns": columns, "child": child}


def select(condition, child):
    return {"op": "select", "condition": condition, "child": child}


def join():
    return {
        "op": "join",
        "condition": "Emp.did = Dept.id",
        "left": scan(),
        "right": scan("Dept"),
    }


def optimize(plan, schema=SCHEMA):
    return push_projections(plan, table_columns=schema)


def test_join_preserves_join_keys():
    result = optimize(project(["Emp.name"], join()))
    joined = result["child"]

    assert joined["op"] == "join"
    assert joined["left"]["columns"] == [
        "Emp.did",
        "Emp.name",
    ]
    assert joined["right"]["columns"] == ["Dept.id"]


def test_join_preserves_requested_right_column():
    result = optimize(project(["Emp.name", "Dept.location"], join()))
    joined = result["child"]

    assert joined["left"]["columns"] == [
        "Emp.did",
        "Emp.name",
    ]
    assert joined["right"]["columns"] == [
        "Dept.id",
        "Dept.location",
    ]


def test_filter_column_is_preserved():
    plan = project(
        ["Emp.name"],
        select("Emp.age > 30", scan()),
    )

    result = optimize(plan)

    assert result["child"]["op"] == "select"
    assert result["child"]["child"]["op"] == "project"
    assert result["child"]["child"]["columns"] == [
        "Emp.age",
        "Emp.name",
    ]


def test_sort_key_is_preserved():
    plan = project(
        ["Emp.name"],
        {
            "op": "sort",
            "keys": [["Emp.age", "desc"]],
            "child": scan(),
        },
    )

    result = optimize(plan)

    assert result["child"]["op"] == "sort"
    assert result["child"]["child"]["columns"] == [
        "Emp.age",
        "Emp.name",
    ]


def test_limit_is_traversed():
    plan = project(
        ["Emp.name"],
        {
            "op": "limit",
            "count": 10,
            "child": select("Emp.age > 30", scan()),
        },
    )

    result = optimize(plan)

    assert result["child"]["op"] == "limit"
    assert result["child"]["child"]["op"] == "select"
    assert result["child"]["child"]["child"]["columns"] == [
        "Emp.age",
        "Emp.name",
    ]


def test_nested_joins():
    plan = project(
        ["Emp.name"],
        {
            "op": "join",
            "condition": "Emp.did = Dept.id",
            "left": {
                "op": "join",
                "condition": "Emp.id = Emp.did",
                "left": scan(),
                "right": scan("Dept"),
            },
            "right": scan("Dept"),
        },
    )

    # Duplicate qualified output names make this ambiguous.
    result = optimize(plan)

    assert result["child"]["op"] == "join"
    assert result["child"]["left"]["op"] == "join"


def test_cross_product_pushdown():
    plan = project(
        ["Emp.name", "Dept.location"],
        {
            "op": "cross",
            "left": scan(),
            "right": scan("Dept"),
        },
    )

    result = optimize(plan)

    assert result["child"]["left"]["columns"] == ["Emp.name"]
    assert result["child"]["right"]["columns"] == ["Dept.location"]


def test_no_root_project_is_unchanged():
    plan = select("Emp.age > 30", scan())

    assert optimize(plan) == plan


def test_select_star_style_plan_is_unchanged():
    plan = scan()

    assert optimize(plan) == plan


def test_missing_schema_is_conservative():
    plan = project(["Emp.name"], scan())

    assert optimize(plan, schema={}) == plan


def test_rename_is_boundary():
    plan = project(
        ["e.name"],
        {
            "op": "rename",
            "to": "e",
            "child": scan(),
        },
    )

    result = optimize(plan)

    assert result["child"]["op"] == "rename"
    assert result["child"]["child"]["op"] == "scan"


def test_group_by_is_boundary():
    plan = project(
        ["Emp.did"],
        {
            "op": "group_by",
            "keys": ["Emp.did"],
            "aggregates": [["count", "*", "count_star"]],
            "child": scan(),
        },
    )

    assert optimize(plan) == plan


def test_union_is_boundary():
    plan = project(
        ["Emp.name"],
        {
            "op": "union_all",
            "left": scan(),
            "right": scan(),
        },
    )

    assert optimize(plan) == plan


def test_aliased_projection_is_boundary():
    plan = {
        "op": "project",
        "columns": ["Emp.name"],
        "aliases": {"employee": "Emp.name"},
        "outputs": ["employee"],
        "child": join(),
    }

    assert optimize(plan) == plan


def test_ambiguous_unqualified_column_is_conservative():
    plan = project(["id"], join())

    assert optimize(plan) == plan


def test_unknown_column_is_conservative():
    plan = project(["Emp.missing"], join())

    assert optimize(plan) == plan


def test_original_plan_not_mutated():
    plan = project(["Emp.name"], join())
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


def test_deterministic():
    plan = project(["Emp.name"], join())

    assert optimize(plan) == optimize(plan)


def test_idempotent():
    plan = project(["Emp.name"], join())

    once = optimize(plan)
    twice = optimize(once)

    assert once == twice
