"""Tests for recursive logical-plan cardinality estimation."""

from copy import deepcopy

import pytest

from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.statistics import (
    ColumnStatistics,
    HistogramBucket,
    TableStatistics,
)


@pytest.fixture
def estimator():
    emp = TableStatistics(
        table="Emp",
        n_tuples=100,
        n_pages=1,
        width=20,
        columns={
            "id": ColumnStatistics(100, 1, 100),
            "age": ColumnStatistics(
                5,
                20,
                60,
                (
                    HistogramBucket(20, 30, 40, 2),
                    HistogramBucket(40, 60, 60, 3),
                ),
            ),
            "did": ColumnStatistics(10, 1, 10),
        },
    )

    dept = TableStatistics(
        table="Dept",
        n_tuples=10,
        n_pages=1,
        width=16,
        columns={
            "id": ColumnStatistics(10, 1, 10),
            "name": ColumnStatistics(10, "A", "Z"),
        },
    )

    return LogicalPlanEstimator(
        {"Emp": emp, "Dept": dept},
        table_columns={
            "Emp": ["id", "age", "did"],
            "Dept": ["id", "name"],
        },
    )


def scan(table="Emp"):
    return {"op": "scan", "table": table}


def test_scan(estimator):
    result = estimator.estimate(scan())

    assert result.rows == 100
    assert result.pages == 1
    assert result.width == 20
    assert "Emp.age" in result.columns


def test_selection(estimator):
    plan = {
        "op": "select",
        "condition": "Emp.id = 5",
        "child": scan(),
    }

    result = estimator.estimate(plan)

    assert result.rows == 1
    assert result.plan["child"]["est_rows"] == 100


def test_histogram_selection(estimator):
    plan = {
        "op": "select",
        "condition": "Emp.age = 30",
        "child": scan(),
    }

    # First bucket: 40 tuples / 2 distinct values / 100 rows.
    assert estimator.estimate(plan).rows == 20


def test_projection_preserves_rows(estimator):
    plan = {
        "op": "project",
        "columns": ["Emp.id", "Emp.age"],
        "child": scan(),
    }

    result = estimator.estimate(plan)

    assert result.rows == 100
    assert result.width == pytest.approx(40 / 3)
    assert set(result.columns) == {"Emp.id", "Emp.age"}


def test_projection_aliases(estimator):
    plan = {
        "op": "project",
        "columns": ["Emp.age"],
        "outputs": ["employee_age"],
        "aliases": {"employee_age": "Emp.age"},
        "child": scan(),
    }

    result = estimator.estimate(plan)

    assert "employee_age" in result.columns
    assert "Emp.age" not in result.columns


def test_rename_preserves_statistics(estimator):
    plan = {
        "op": "select",
        "condition": "e.age = 30",
        "child": {
            "op": "rename",
            "to": "e",
            "child": scan(),
        },
    }

    result = estimator.estimate(plan)

    assert result.rows == 20
    assert "e.age" in result.columns


def test_cross_product(estimator):
    plan = {
        "op": "cross",
        "left": scan(),
        "right": scan("Dept"),
    }

    assert estimator.estimate(plan).rows == 1000


def test_equality_join(estimator):
    plan = {
        "op": "join",
        "condition": "Emp.did = Dept.id",
        "left": scan(),
        "right": scan("Dept"),
    }

    assert estimator.estimate(plan).rows == 100


def test_filter_above_join_uses_source_histogram(estimator):
    plan = {
        "op": "select",
        "condition": "Emp.age = 30",
        "child": {
            "op": "join",
            "condition": "Emp.did = Dept.id",
            "left": scan(),
            "right": scan("Dept"),
        },
    }

    # Join produces 100 rows. Emp.age selectivity remains 0.2.
    assert estimator.estimate(plan).rows == 20


def test_join_with_aliases(estimator):
    plan = {
        "op": "join",
        "condition": "e.did = d.id",
        "left": {
            "op": "rename",
            "to": "e",
            "child": scan(),
        },
        "right": {
            "op": "rename",
            "to": "d",
            "child": scan("Dept"),
        },
    }

    assert estimator.estimate(plan).rows == 100


def test_group_by(estimator):
    plan = {
        "op": "group_by",
        "keys": ["Emp.did"],
        "aggregates": [["count", "*", "count_star"]],
        "child": scan(),
    }

    result = estimator.estimate(plan)

    assert result.rows == 10
    assert "count_star" in result.columns


def test_global_aggregation(estimator):
    plan = {
        "op": "group_by",
        "keys": [],
        "aggregates": [["count", "*", "count_star"]],
        "child": scan(),
    }

    assert estimator.estimate(plan).rows == 1


def test_sort_preserves_rows(estimator):
    plan = {
        "op": "sort",
        "keys": [["Emp.age", "asc"]],
        "child": scan(),
    }

    assert estimator.estimate(plan).rows == 100


def test_distinct(estimator):
    plan = {
        "op": "distinct",
        "child": {
            "op": "project",
            "columns": ["Emp.did"],
            "child": scan(),
        },
    }

    assert estimator.estimate(plan).rows == 10


def test_limit(estimator):
    plan = {
        "op": "limit",
        "count": 5,
        "child": scan(),
    }

    assert estimator.estimate(plan).rows == 5


def test_limit_zero(estimator):
    plan = {
        "op": "limit",
        "count": 0,
        "child": scan(),
    }

    assert estimator.estimate(plan).rows == 0


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("union_all", 110),
        ("union", 100),
        ("intersect", 5),
        ("except", 95),
    ],
)
def test_set_operations(estimator, operator, expected):
    plan = {
        "op": operator,
        "left": scan(),
        "right": scan("Dept"),
    }

    assert estimator.estimate(plan).rows == expected


def test_missing_table_statistics(estimator):
    result = estimator.estimate({"op": "scan", "table": "Unknown"})

    assert result.rows == 1000
    assert result.width == 16


def test_missing_column_statistics(estimator):
    plan = {
        "op": "select",
        "condition": "Emp.salary = 5000",
        "child": scan(),
    }

    assert estimator.estimate(plan).rows == 10


def test_original_plan_not_mutated(estimator):
    plan = {
        "op": "select",
        "condition": "Emp.age = 30",
        "child": scan(),
    }
    original = deepcopy(plan)

    annotated = estimator.annotate(plan)

    assert plan == original
    assert annotated["est_rows"] == 20
    assert annotated["child"]["est_rows"] == 100


def test_invalid_operator(estimator):
    with pytest.raises(ValueError, match="Unsupported"):
        estimator.estimate({"op": "unknown"})


def test_nested_logical_plan(estimator):
    plan = {
        "op": "limit",
        "count": 3,
        "child": {
            "op": "sort",
            "keys": [["Emp.age", "asc"]],
            "child": {
                "op": "project",
                "columns": ["Emp.age"],
                "child": {
                    "op": "select",
                    "condition": "Emp.age = 30",
                    "child": scan(),
                },
            },
        },
    }

    result = estimator.estimate(plan)

    assert result.rows == 3
    assert result.plan["child"]["est_rows"] == 20
    assert result.plan["child"]["child"]["est_rows"] == 20
    assert result.plan["child"]["child"]["child"]["est_rows"] == 20
