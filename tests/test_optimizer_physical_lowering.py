"""Tests for safe lowering into Module 2 physical plan JSON."""

from copy import deepcopy

import pytest

from src.optimizer.physical_lowering import (
    UnsupportedPhysicalPlan,
    lower_physical_plan,
)
from src.optimizer.statistics import TableStatistics

SCHEMA = {
    "A": ["id", "value"],
    "B": ["id", "value"],
    "C": ["id", "value"],
}

STATS = {
    name: TableStatistics(
        table=name,
        n_tuples=1000,
        n_pages=pages,
        width=16.0,
    )
    for name, pages in (("A", 100), ("B", 10), ("C", 50))
}


def scan(table):
    return {"op": "scan", "table": table}


def join(left, right, condition="A.id = B.id"):
    return {
        "op": "join",
        "condition": condition,
        "left": left,
        "right": right,
    }


def lower(plan, **kwargs):
    return lower_physical_plan(
        plan,
        STATS,
        table_columns=SCHEMA,
        **kwargs,
    )


def test_scan_lowering():
    assert lower(scan("A")) == {
        "op": "seqscan",
        "table": "A",
    }


def test_project_lowering():
    plan = {
        "op": "project",
        "columns": ["A.id"],
        "child": scan("A"),
    }

    result = lower(plan)

    assert result["op"] == "project"
    assert result["columns"] == ["A.id"]
    assert result["child"]["op"] == "seqscan"


def test_simple_filter_lowering():
    plan = {
        "op": "select",
        "condition": "A.value > 10",
        "child": scan("A"),
    }

    result = lower(plan)

    assert result["op"] == "filter"
    assert result["column"] == "A.value"
    assert result["comparison"] == ">"
    assert result["value"] == 10


def test_limit_lowering():
    plan = {
        "op": "limit",
        "count": 5,
        "child": scan("A"),
    }

    assert lower(plan)["op"] == "limit"


def test_equality_join_lowering():
    result = lower(join(scan("A"), scan("B")))

    assert result["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    assert {result["left_key"], result["right_key"]} == {
        "A.id",
        "B.id",
    }

    assert result["left_key"].split(".")[0] == result["left"]["table"]
    assert result["right_key"].split(".")[0] == result["right"]["table"]


def test_reversed_join_condition_oriented():
    result = lower(join(scan("A"), scan("B"), "B.id = A.id"))

    assert {result["left_key"], result["right_key"]} == {
        "A.id",
        "B.id",
    }

    assert result["left_key"].split(".")[0] == result["left"]["table"]
    assert result["right_key"].split(".")[0] == result["right"]["table"]


def test_nested_join_lowering():
    plan = join(
        join(scan("A"), scan("B")),
        scan("C"),
        "B.id = C.id",
    )

    result = lower(plan)

    assert result["right"]["op"] == "seqscan"
    assert result["right"]["table"] == "C"
    assert result["left"]["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }


def test_compound_join_rejected():
    plan = join(
        scan("A"),
        scan("B"),
        "(A.id = B.id AND A.value = B.value)",
    )

    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="one equality predicate",
    ):
        lower(plan)


def test_non_equality_join_rejected():
    plan = join(scan("A"), scan("B"), "A.id > B.id")

    with pytest.raises(UnsupportedPhysicalPlan):
        lower(plan)


def test_cross_join_rejected():
    plan = {
        "op": "cross",
        "left": scan("A"),
        "right": scan("B"),
    }

    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="Unsupported logical operator",
    ):
        lower(plan)


def test_alias_rejected():
    plan = {
        "op": "rename",
        "to": "a",
        "child": scan("A"),
    }

    with pytest.raises(UnsupportedPhysicalPlan):
        lower(plan)


def test_compound_filter_rejected():
    plan = {
        "op": "select",
        "condition": "(A.value > 10 OR A.id < 50)",
        "child": scan("A"),
    }

    with pytest.raises(UnsupportedPhysicalPlan):
        lower(plan)


def test_missing_statistics_uses_fallback_for_join():
    plan = join(scan("A"), scan("B"))

    physical = lower_physical_plan(
        plan,
        {"A": STATS["A"]},
        table_columns=SCHEMA,
    )

    assert physical["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    assert physical["left"]["op"] == "seqscan"
    assert physical["right"]["op"] == "seqscan"

    assert {physical["left"]["table"], physical["right"]["table"]} == {
        "A",
        "B",
    }


def test_unknown_column_rejected():
    plan = {
        "op": "project",
        "columns": ["A.missing"],
        "child": scan("A"),
    }

    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="Column is unavailable",
    ):
        lower(plan)


def test_original_plan_not_mutated():
    plan = join(scan("A"), scan("B"))
    original = deepcopy(plan)

    lower(plan)

    assert plan == original


def test_deterministic_lowering():
    plan = join(scan("A"), scan("B"))

    assert lower(plan) == lower(plan)


def test_invalid_frames_rejected():
    with pytest.raises(ValueError):
        lower(scan("A"), frames=2)


def test_buffer_frames_change_join_algorithm():
    from src.optimizer.statistics import TableStatistics

    statistics = {
        "A": TableStatistics(
            table="A",
            n_tuples=10000,
            n_pages=100,
            width=40.0,
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=10000,
            n_pages=100,
            width=40.0,
        ),
    }

    plan = join(scan("A"), scan("B"))

    small_buffers = lower_physical_plan(
        plan,
        statistics,
        table_columns=SCHEMA,
        frames=4,
    )

    large_buffers = lower_physical_plan(
        plan,
        statistics,
        table_columns=SCHEMA,
        frames=128,
    )

    assert small_buffers["op"] == "hash_join"
    assert large_buffers["op"] == "nested_loop_join"


def test_nested_loop_uses_cheapest_outer_orientation():
    """Physical lowering must use the orientation costed by DP."""

    statistics = {
        "A": TableStatistics(
            table="A",
            n_tuples=5000,
            n_pages=100,
            width=40.0,
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=500,
            n_pages=10,
            width=40.0,
        ),
    }

    plan = join(scan("A"), scan("B"))

    physical = lower_physical_plan(
        plan,
        statistics,
        table_columns=SCHEMA,
        frames=32,
    )

    assert physical["op"] == "nested_loop_join"
    assert physical["left"] == {"op": "seqscan", "table": "B"}
    assert physical["right"] == {"op": "seqscan", "table": "A"}
    assert physical["left_key"] == "B.id"
    assert physical["right_key"] == "A.id"


def test_nested_loop_preserves_already_optimal_orientation():
    """Do not swap inputs when the left side is already cheaper."""

    statistics = {
        "A": TableStatistics(
            table="A",
            n_tuples=500,
            n_pages=10,
            width=40.0,
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=5000,
            n_pages=100,
            width=40.0,
        ),
    }

    physical = lower_physical_plan(
        join(scan("A"), scan("B")),
        statistics,
        table_columns=SCHEMA,
        frames=32,
    )

    assert physical["op"] == "nested_loop_join"
    assert physical["left"]["table"] == "A"
    assert physical["right"]["table"] == "B"
    assert physical["left_key"] == "A.id"
    assert physical["right_key"] == "B.id"


def test_hash_join_preserves_input_orientation():
    """Nested-loop orientation must not reorder a hash join."""

    statistics = {
        "A": TableStatistics(
            table="A",
            n_tuples=10000,
            n_pages=100,
            width=40.0,
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=10000,
            n_pages=100,
            width=40.0,
        ),
    }

    physical = lower_physical_plan(
        join(scan("A"), scan("B")),
        statistics,
        table_columns=SCHEMA,
        frames=4,
    )

    assert physical["op"] == "hash_join"
    assert physical["left"]["table"] == "A"
    assert physical["right"]["table"] == "B"
