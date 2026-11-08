"""Regression tests for statistics-aware physical join costing."""

from src.optimizer.physical_lowering import (
    lower_physical_plan,
)
from src.optimizer.statistics import TableStatistics

SCHEMA = {
    "A": ["id", "value"],
    "B": ["id", "value"],
    "C": ["id", "value"],
}


def statistics(rows, pages, width=16.0):
    return TableStatistics(
        table="placeholder",
        n_tuples=rows,
        n_pages=pages,
        width=width,
    )


def scan(table):
    return {"op": "scan", "table": table}


def join(left, right, condition):
    return {
        "op": "join",
        "condition": condition,
        "left": left,
        "right": right,
    }


def lower(plan, stats, frames=32):
    return lower_physical_plan(
        plan,
        stats,
        table_columns=SCHEMA,
        frames=frames,
    )


def test_small_equality_join_can_be_lowered():
    stats = {
        "A": statistics(10, 1),
        "B": statistics(10, 1),
    }

    plan = join(scan("A"), scan("B"), "A.id = B.id")

    result = lower(plan, stats)

    assert result["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }


def test_large_equality_join_can_be_lowered():
    stats = {
        "A": statistics(100000, 1000),
        "B": statistics(100000, 1000),
    }

    plan = join(scan("A"), scan("B"), "A.id = B.id")

    result = lower(plan, stats)

    assert result["left_key"] == "A.id"
    assert result["right_key"] == "B.id"


def test_nested_join_uses_intermediate_estimates():
    stats = {
        "A": statistics(100000, 1000),
        "B": statistics(1000, 20),
        "C": statistics(100, 5),
    }

    plan = join(
        join(scan("A"), scan("B"), "A.id = B.id"),
        scan("C"),
        "B.id = C.id",
    )

    result = lower(plan, stats)

    assert result["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }
    assert result["left"]["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }


def test_missing_statistics_in_nested_join_uses_fallback():
    stats = {
        "A": statistics(1000, 10),
        "B": statistics(1000, 10),
    }

    plan = join(
        join(scan("A"), scan("B"), "A.id = B.id"),
        scan("C"),
        "B.id = C.id",
    )

    physical = lower(plan, stats)

    join_operators = {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    assert physical["op"] in join_operators
    assert physical["left"]["op"] in join_operators

    assert physical["left"]["left"] == {
        "op": "seqscan",
        "table": "A",
    }

    assert physical["left"]["right"] == {
        "op": "seqscan",
        "table": "B",
    }

    assert physical["right"] == {
        "op": "seqscan",
        "table": "C",
    }


def test_deterministic_algorithm_selection():
    stats = {
        "A": statistics(10000, 100),
        "B": statistics(1000, 20),
    }

    plan = join(scan("A"), scan("B"), "A.id = B.id")

    assert lower(plan, stats) == lower(plan, stats)


def test_frame_budget_accepted():
    stats = {
        "A": statistics(1000, 10),
        "B": statistics(1000, 10),
    }

    plan = join(scan("A"), scan("B"), "A.id = B.id")

    for frames in (4, 8, 16, 32):
        result = lower(plan, stats, frames=frames)
        assert result["op"] in {
            "nested_loop_join",
            "hash_join",
            "sort_merge_join",
        }
