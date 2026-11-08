"""Tests for Module 2 join compatibility checks."""

from copy import deepcopy

import pytest

from src.optimizer.physical_compatibility import (
    check_join_compatibility,
)

SCHEMAS = {
    "A": ["id", "value"],
    "B": ["id", "value"],
}


def scan(table):
    return {"op": "scan", "table": table}


def join(condition, left=None, right=None):
    return {
        "op": "join",
        "condition": condition,
        "left": left if left is not None else scan("A"),
        "right": right if right is not None else scan("B"),
    }


def check(plan):
    return check_join_compatibility(
        plan,
        table_columns=SCHEMAS,
    )


def test_simple_equijoin():
    result = check(join("A.id = B.id"))

    assert result.supported
    assert result.left_key == "A.id"
    assert result.right_key == "B.id"


def test_reversed_equality():
    result = check(join("B.id = A.id"))

    assert result.supported
    assert result.left_key == "A.id"
    assert result.right_key == "B.id"


def test_aliases():
    plan = join(
        "a.id = b.id",
        {"op": "rename", "to": "a", "child": scan("A")},
        {"op": "rename", "to": "b", "child": scan("B")},
    )

    result = check(plan)

    assert result.supported
    assert result.left_key == "a.id"
    assert result.right_key == "b.id"


def test_projection_preserves_join_keys():
    plan = join(
        "A.id = B.id",
        {
            "op": "project",
            "columns": ["A.id"],
            "child": scan("A"),
        },
        scan("B"),
    )

    assert check(plan).supported


def test_projection_removes_join_key():
    plan = join(
        "A.id = B.id",
        {
            "op": "project",
            "columns": ["A.value"],
            "child": scan("A"),
        },
        scan("B"),
    )

    assert not check(plan).supported


@pytest.mark.parametrize(
    "condition",
    [
        "A.id < B.id",
        "A.id != B.id",
        "A.id = 10",
        "A.id = A.value",
        "A.id = A.id",
        "(A.id = B.id AND A.value > 10)",
    ],
)
def test_unsupported_join_conditions(condition):
    assert not check(join(condition)).supported


def test_missing_schema():
    result = check_join_compatibility(
        join("A.id = B.id"),
        table_columns={"A": ["id"]},
    )

    assert not result.supported


def test_cross_join_rejected():
    result = check(
        {
            "op": "cross",
            "left": scan("A"),
            "right": scan("B"),
        }
    )

    assert not result.supported


def test_unsupported_child_schema():
    plan = join(
        "A.id = B.id",
        {"op": "group_by", "keys": ["A.id"], "child": scan("A")},
        scan("B"),
    )

    assert not check(plan).supported


def test_does_not_mutate_input():
    plan = join("A.id = B.id")
    original = deepcopy(plan)

    check(plan)

    assert plan == original


def test_deterministic():
    plan = join("A.id = B.id")

    assert check(plan) == check(plan)
