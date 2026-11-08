"""Tests for explicit physical join-algorithm selection."""

import pytest

from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.statistics import TableStatistics

TABLE_COLUMNS = {
    "A": ["id"],
    "B": ["id"],
}

STATISTICS = {
    "A": TableStatistics(
        table="A",
        n_tuples=100,
        n_pages=2,
        width=16.0,
    ),
    "B": TableStatistics(
        table="B",
        n_tuples=200,
        n_pages=4,
        width=16.0,
    ),
}

JOIN_PLAN = {
    "op": "join",
    "condition": "A.id = B.id",
    "left": {"op": "scan", "table": "A"},
    "right": {"op": "scan", "table": "B"},
}


@pytest.mark.parametrize(
    "algorithm",
    [
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    ],
)
def test_forced_join_algorithm(algorithm):
    physical = lower_physical_plan(
        JOIN_PLAN,
        STATISTICS,
        table_columns=TABLE_COLUMNS,
        frames=32,
        join_algorithm=algorithm,
    )

    assert physical["op"] == algorithm


def test_default_join_algorithm_is_cost_based():
    physical = lower_physical_plan(
        JOIN_PLAN,
        STATISTICS,
        table_columns=TABLE_COLUMNS,
        frames=32,
    )

    assert physical["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }


def test_invalid_join_algorithm_is_rejected():
    with pytest.raises(ValueError, match="Unsupported join algorithm"):
        lower_physical_plan(
            JOIN_PLAN,
            STATISTICS,
            table_columns=TABLE_COLUMNS,
            frames=32,
            join_algorithm="invalid_join",
        )


def test_preserve_join_order_keeps_written_inputs():
    physical = lower_physical_plan(
        JOIN_PLAN,
        STATISTICS,
        table_columns=TABLE_COLUMNS,
        frames=32,
        join_algorithm="nested_loop_join",
        preserve_join_order=True,
    )

    assert physical["op"] == "nested_loop_join"
    assert physical["left"] == {"op": "seqscan", "table": "A"}
    assert physical["right"] == {"op": "seqscan", "table": "B"}
