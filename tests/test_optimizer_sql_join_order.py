"""Tests for conservative SQL logical join-order integration."""

from copy import deepcopy

import pytest

from src.optimizer.sql_join_order import optimize_sql_join_order
from src.optimizer.statistics import TableStatistics

SCHEMAS = {name: ["id", "value"] for name in "ABCD"}

STATS = {
    name: TableStatistics(
        table=name,
        n_tuples=pages * 100,
        n_pages=pages,
        width=40.0,
    )
    for name, pages in [
        ("A", 100),
        ("B", 10),
        ("C", 400),
        ("D", 50),
    ]
}


def scan(table):
    return {"op": "scan", "table": table}


def join(left, right, condition):
    return {
        "op": "join",
        "condition": condition,
        "left": left,
        "right": right,
    }


def chain():
    return join(
        join(scan("A"), scan("B"), "A.id = B.id"),
        scan("C"),
        "B.id = C.id",
    )


def optimize(plan, statistics=None, schemas=None):
    return optimize_sql_join_order(
        plan,
        STATS if statistics is None else statistics,
        table_columns=SCHEMAS if schemas is None else schemas,
    )


def scans(plan):
    if plan["op"] == "scan":
        return [plan["table"]]

    result = []
    for key in ("child", "left", "right"):
        child = plan.get(key)
        if isinstance(child, dict):
            result.extend(scans(child))

    return result


def test_two_table_join():
    plan = join(scan("A"), scan("B"), "A.id = B.id")

    result = optimize(plan)

    assert result["op"] == "join"
    assert sorted(scans(result)) == ["A", "B"]


def test_three_table_join():
    result = optimize(chain())

    assert sorted(scans(result)) == ["A", "B", "C"]
    assert result["op"] == "join"


def test_four_table_join():
    plan = join(
        chain(),
        scan("D"),
        "C.id = D.id",
    )

    result = optimize(plan)

    assert sorted(scans(result)) == ["A", "B", "C", "D"]


def test_filter_and_projection_preserved():
    plan = {
        "op": "project",
        "columns": ["A.id"],
        "child": {
            "op": "select",
            "condition": "A.value > 10",
            "child": chain(),
        },
    }

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["columns"] == ["A.id"]
    assert result["child"]["op"] == "select"
    assert result["child"]["condition"] == "A.value > 10"
    assert sorted(scans(result)) == ["A", "B", "C"]


def test_alias_join_unchanged():
    plan = join(
        {"op": "rename", "to": "a", "child": scan("A")},
        {"op": "rename", "to": "b", "child": scan("B")},
        "a.id = b.id",
    )

    assert optimize(plan) == plan


def test_cross_join_unchanged():
    plan = {
        "op": "cross",
        "left": scan("A"),
        "right": scan("B"),
    }

    assert optimize(plan) == plan


def test_non_equality_join_unchanged():
    plan = join(scan("A"), scan("B"), "A.id < B.id")

    assert optimize(plan) == plan


def test_missing_statistics_preserves_plan():
    plan = chain()
    available = {"A": STATS["A"], "B": STATS["B"]}

    result = optimize(plan, statistics=available)

    # The A-B subtree may still be optimized independently,
    # but the full A-B-C tree cannot be reordered.
    assert sorted(scans(result)) == ["A", "B", "C"]
    assert result["condition"] == "B.id = C.id"


def test_missing_schema_preserves_plan():
    plan = join(scan("A"), scan("B"), "A.id = B.id")

    result = optimize(
        plan,
        schemas={"A": ["id"]},
    )

    assert result == plan


def test_unknown_column_preserves_plan():
    plan = join(scan("A"), scan("B"), "A.missing = B.id")

    assert optimize(plan) == plan


def test_deterministic():
    plan = chain()

    assert optimize(plan) == optimize(plan)


def test_input_not_mutated():
    plan = chain()
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


def test_invalid_buffer_count():
    with pytest.raises(ValueError):
        optimize_sql_join_order(
            chain(),
            STATS,
            table_columns=SCHEMAS,
            frames=2,
        )


def test_reversed_join_keys_supported():
    plan = join(scan("A"), scan("B"), "B.id = A.id")

    result = optimize(plan)

    assert sorted(scans(result)) == ["A", "B"]


def test_same_side_equality_not_reordered():
    plan = join(scan("A"), scan("B"), "A.id = A.value")

    assert optimize(plan) == plan
