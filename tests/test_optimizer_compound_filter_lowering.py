"""Tests for lowering compound AND predicates."""

import pytest

from src.optimizer.physical_lowering import (
    UnsupportedPhysicalPlan,
    lower_physical_plan,
)
from src.optimizer.statistics import TableStatistics

TABLE_COLUMNS = {
    "Customers": ["cid", "region", "tier", "age"],
}

STATISTICS = {
    "Customers": TableStatistics(
        table="Customers",
        n_tuples=240,
        n_pages=2,
        width=16.0,
    ),
}


def lower(condition):
    return lower_physical_plan(
        {
            "op": "select",
            "condition": condition,
            "child": {
                "op": "scan",
                "table": "Customers",
            },
        },
        STATISTICS,
        table_columns=TABLE_COLUMNS,
    )


def test_simple_filter():
    result = lower("Customers.region = 1")

    assert result["op"] == "filter"
    assert result["column"] == "Customers.region"
    assert result["child"]["op"] == "seqscan"


def test_compound_and_filter():
    result = lower("Customers.region = 1 AND Customers.tier = 1")

    assert result["op"] == "filter"
    assert result["column"] == "Customers.tier"

    inner = result["child"]

    assert inner["op"] == "filter"
    assert inner["column"] == "Customers.region"
    assert inner["child"] == {
        "op": "seqscan",
        "table": "Customers",
    }


def test_three_predicates():
    result = lower(
        "Customers.region = 1 AND Customers.tier = 1 AND Customers.age >= 20"
    )

    columns = []

    while result["op"] == "filter":
        columns.append(result["column"])
        result = result["child"]

    assert columns == [
        "Customers.age",
        "Customers.tier",
        "Customers.region",
    ]
    assert result["op"] == "seqscan"


def test_parenthesized_and():
    result = lower("(Customers.region = 1 AND Customers.tier = 1)")

    assert result["op"] == "filter"
    assert result["child"]["op"] == "filter"


def test_or_remains_unsupported():
    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="Only AND compound filters",
    ):
        lower("Customers.region = 1 OR Customers.tier = 1")


def test_not_remains_unsupported():
    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="column-to-literal",
    ):
        lower("NOT Customers.region = 1")


def test_unknown_column_rejected():
    with pytest.raises(
        UnsupportedPhysicalPlan,
        match="Column is unavailable",
    ):
        lower("Customers.region = 1 AND Customers.missing = 2")
