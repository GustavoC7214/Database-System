"""Tests for Module 4 cardinality measurement helpers."""

import pytest

from experiments.m4.measure_cardinality import (
    iter_nodes,
    q_error,
)


@pytest.mark.parametrize(
    ("estimated", "actual", "expected"),
    [
        (100, 100, 1.0),
        (50, 100, 2.0),
        (100, 50, 2.0),
        (25, 100, 4.0),
        (100, 25, 4.0),
        (0, 0, 1.0),
        (0, 10, 10.0),
        (10, 0, 10.0),
        (0, 1, 1.0),
        (1, 0, 1.0),
    ],
)
def test_q_error(estimated, actual, expected):
    assert q_error(estimated, actual) == expected


@pytest.mark.parametrize(
    ("estimated", "actual"),
    [
        (-1, 10),
        (10, -1),
        (-1, -1),
    ],
)
def test_q_error_rejects_negative_cardinalities(
    estimated,
    actual,
):
    with pytest.raises(ValueError):
        q_error(estimated, actual)


def test_iter_nodes_unary_plan():
    plan = {
        "op": "select",
        "condition": "A.id = 1",
        "child": {
            "op": "scan",
            "table": "A",
        },
    }

    nodes = list(iter_nodes(plan))

    assert [path for path, _ in nodes] == [
        "root",
        "root.child",
    ]
    assert [node["op"] for _, node in nodes] == [
        "select",
        "scan",
    ]


def test_iter_nodes_join_plan():
    plan = {
        "op": "join",
        "condition": "A.id = B.id",
        "left": {
            "op": "scan",
            "table": "A",
        },
        "right": {
            "op": "scan",
            "table": "B",
        },
    }

    nodes = list(iter_nodes(plan))

    assert [path for path, _ in nodes] == [
        "root",
        "root.left",
        "root.right",
    ]


def test_iter_nodes_does_not_modify_plan():
    plan = {
        "op": "scan",
        "table": "Customers",
    }

    list(iter_nodes(plan))

    assert plan == {
        "op": "scan",
        "table": "Customers",
    }
