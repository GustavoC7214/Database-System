"""Tests for cardinality estimates without column statistics."""

from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.statistics import TableStatistics


def make_estimator():
    stats = {
        "A": TableStatistics(
            table="A",
            n_tuples=1000,
            n_pages=20,
            width=16.0,
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=100,
            n_pages=5,
            width=16.0,
        ),
    }

    return LogicalPlanEstimator(
        stats,
        table_columns={
            "A": ["id", "value"],
            "B": ["id"],
        },
    )


def test_equality_without_column_statistics():
    estimator = make_estimator()

    plan = {
        "op": "select",
        "condition": "A.value = 10",
        "child": {"op": "scan", "table": "A"},
    }

    assert estimator.estimate(plan).rows == 100


def test_range_without_column_statistics():
    estimator = make_estimator()

    plan = {
        "op": "select",
        "condition": "A.value > 10",
        "child": {"op": "scan", "table": "A"},
    }

    assert estimator.estimate(plan).rows == 334


def test_join_without_column_statistics():
    estimator = make_estimator()

    plan = {
        "op": "join",
        "condition": "A.id = B.id",
        "left": {"op": "scan", "table": "A"},
        "right": {"op": "scan", "table": "B"},
    }

    assert estimator.estimate(plan).rows == 10000


def test_estimator_does_not_modify_input():
    estimator = make_estimator()

    plan = {
        "op": "select",
        "condition": "A.value = 10",
        "child": {"op": "scan", "table": "A"},
    }

    original = {
        "op": "select",
        "condition": "A.value = 10",
        "child": {"op": "scan", "table": "A"},
    }

    estimator.estimate(plan)

    assert plan == original
