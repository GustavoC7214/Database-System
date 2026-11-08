"""Tests for recursive physical I/O cost estimation."""

from copy import deepcopy

import pytest

from src.optimizer.plan_cost import PhysicalCostEstimator
from src.optimizer.statistics import TableStatistics

STATS = {
    "A": TableStatistics(
        table="A",
        n_tuples=10000,
        n_pages=100,
        width=40.0,
    ),
    "B": TableStatistics(
        table="B",
        n_tuples=40000,
        n_pages=400,
        width=40.0,
    ),
}


def scan(table):
    return {"op": "scan", "table": table}


def join():
    return {
        "op": "join",
        "condition": "A.id = B.id",
        "left": scan("A"),
        "right": scan("B"),
    }


def estimator(frames=32):
    return PhysicalCostEstimator(
        STATS,
        frames=frames,
        table_columns={
            "A": ["id", "value"],
            "B": ["id", "value"],
        },
    )


def test_scan_cost():
    result = estimator().estimate(scan("A"))

    assert result.algorithm == "seqscan"
    assert result.pages == 100
    assert result.local_io == 100
    assert result.total_io == 100


def test_filter_adds_no_local_io():
    plan = {
        "op": "select",
        "condition": "A.id > 100",
        "child": scan("A"),
    }

    result = estimator().estimate(plan)

    assert result.algorithm == "filter"
    assert result.local_io == 0
    assert result.total_io == 100


def test_project_adds_no_local_io():
    plan = {
        "op": "project",
        "columns": ["A.id"],
        "child": scan("A"),
    }

    result = estimator().estimate(plan)

    assert result.local_io == 0
    assert result.total_io == 100


def test_sort_adds_sort_cost():
    plan = {
        "op": "sort",
        "keys": [["A.id", "asc"]],
        "child": scan("A"),
    }

    result = estimator().estimate(plan)

    assert result.algorithm == "external_sort"
    assert result.local_io == 300
    assert result.total_io == 400


def test_hash_join_selected():
    result = estimator().estimate(join())

    assert result.algorithm == "hash_join"
    assert result.local_io == 1500
    assert result.total_io == 2000


def test_more_frames_changes_join_algorithm():
    small = estimator(frames=32).estimate(join())
    large = estimator(frames=512).estimate(join())

    assert small.algorithm == "hash_join"
    assert large.algorithm == "nested_loop_join:left"
    assert large.total_io < small.total_io


def test_cross_uses_nested_loop():
    plan = {
        "op": "cross",
        "left": scan("A"),
        "right": scan("B"),
    }

    result = estimator().estimate(plan)

    assert result.algorithm.startswith("nested_loop_join:")
    assert result.local_io == 1700


def test_nested_plan_costs_children():
    plan = {
        "op": "sort",
        "keys": [["A.id", "asc"]],
        "child": {
            "op": "select",
            "condition": "A.id > 100",
            "child": scan("A"),
        },
    }

    result = estimator().estimate(plan)

    assert len(result.children) == 1
    assert result.children[0].algorithm == "filter"
    assert result.children[0].children[0].algorithm == "seqscan"
    assert result.total_io >= result.children[0].total_io


def test_union_all_has_no_additional_io():
    plan = {
        "op": "union_all",
        "left": scan("A"),
        "right": scan("B"),
    }

    result = estimator().estimate(plan)

    assert result.algorithm == "union_all"
    assert result.local_io == 0
    assert result.total_io == 500


def test_union_accounts_for_duplicate_elimination():
    plan = {
        "op": "union",
        "left": scan("A"),
        "right": scan("B"),
    }

    result = estimator().estimate(plan)

    assert result.local_io > 0
    assert result.total_io > 500


def test_cost_estimation_does_not_mutate_plan():
    plan = join()
    original = deepcopy(plan)

    estimator().estimate(plan)

    assert plan == original


def test_cost_estimation_is_deterministic():
    plan = join()

    first = estimator().estimate(plan)
    second = estimator().estimate(plan)

    assert first == second


@pytest.mark.parametrize("frames", [0, 1, 2])
def test_insufficient_frames_rejected(frames):
    with pytest.raises(ValueError):
        estimator(frames)


def test_invalid_frames_type():
    with pytest.raises(TypeError):
        estimator(3.5)


def test_unsupported_operator_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        estimator().estimate({"op": "unknown"})
