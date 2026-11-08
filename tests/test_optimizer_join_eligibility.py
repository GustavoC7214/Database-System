"""Tests for physical join algorithm eligibility."""

from copy import deepcopy

import pytest

from src.optimizer.plan_cost import (
    PhysicalCostEstimator,
    is_equijoin_condition,
)
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


def estimator(frames=32):
    return PhysicalCostEstimator(
        STATS,
        frames=frames,
        table_columns={
            "A": ["id", "value"],
            "B": ["id", "value"],
        },
    )


def join(condition):
    return {
        "op": "join",
        "condition": condition,
        "left": {"op": "scan", "table": "A"},
        "right": {"op": "scan", "table": "B"},
    }


@pytest.mark.parametrize(
    "condition",
    [
        "A.id = B.id",
        "B.id = A.id",
        "(A.id = B.id)",
        "A.value = B.value",
    ],
)
def test_simple_equijoin_is_eligible(condition):
    assert is_equijoin_condition(condition)


@pytest.mark.parametrize(
    "condition",
    [
        "A.id < B.id",
        "A.id > B.id",
        "A.id != B.id",
        "A.id <= B.id",
        "A.id = 10",
        "A.id = A.id",
        "(A.id = B.id AND A.value > 10)",
        "(A.id = B.id OR A.value = B.value)",
    ],
)
def test_other_predicates_not_eligible(condition):
    assert not is_equijoin_condition(condition)


def test_equijoin_selects_hash_join():
    result = estimator().estimate(join("A.id = B.id"))

    assert result.algorithm == "hash_join"
    assert result.local_io == 1500


@pytest.mark.parametrize(
    "condition",
    [
        "A.id < B.id",
        "A.id > B.id",
        "A.id != B.id",
    ],
)
def test_non_equality_uses_nested_loop_cost(condition):
    result = estimator().estimate(join(condition))

    assert result.algorithm == "nested_loop_join:left"
    assert result.local_io == 1700


def test_cross_join_never_selects_hash():
    plan = {
        "op": "cross",
        "left": {"op": "scan", "table": "A"},
        "right": {"op": "scan", "table": "B"},
    }

    result = estimator().estimate(plan)

    assert result.algorithm == "nested_loop_join:left"


def test_more_buffers_can_change_equijoin_algorithm():
    plan = join("A.id = B.id")

    small = estimator(32).estimate(plan)
    large = estimator(512).estimate(plan)

    assert small.algorithm == "hash_join"
    assert large.algorithm == "nested_loop_join:left"


def test_join_costing_does_not_mutate_plan():
    plan = join("A.id = B.id")
    original = deepcopy(plan)

    estimator().estimate(plan)

    assert plan == original


def test_join_costing_is_deterministic():
    plan = join("A.id = B.id")

    assert estimator().estimate(plan) == estimator().estimate(plan)
