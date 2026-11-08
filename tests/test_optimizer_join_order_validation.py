"""Validation tests for Selinger join-order inputs."""

from copy import deepcopy

import pytest

from src.optimizer.join_order import JoinEdge, optimize_join_order
from src.optimizer.statistics import ColumnStatistics, TableStatistics


def table(name, *, with_columns=True):
    columns = {}

    if with_columns:
        columns = {
            "id": ColumnStatistics(
                ndv=100,
                minimum=1,
                maximum=100,
            ),
            "key": ColumnStatistics(
                ndv=50,
                minimum=1,
                maximum=50,
            ),
        }

    return TableStatistics(
        table=name,
        n_tuples=1000,
        n_pages=10,
        width=40.0,
        columns=columns,
    )


def stats(*names, with_columns=True):
    return {name: table(name, with_columns=with_columns) for name in names}


def test_duplicate_predicate_rejected():
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("A", "id", "B", "id"),
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        optimize_join_order(stats("A", "B"), edges)


def test_reversed_duplicate_rejected():
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("B", "id", "A", "id"),
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        optimize_join_order(stats("A", "B"), edges)


def test_distinct_predicates_allowed():
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("A", "key", "B", "key"),
    ]

    result = optimize_join_order(stats("A", "B"), edges)

    assert len(result.best.order) == 2
    assert "AND" in result.best.plan["condition"]


@pytest.mark.parametrize(
    ("left_column", "right_column"),
    [
        ("missing", "id"),
        ("id", "missing"),
        ("missing", "missing"),
    ],
)
def test_unknown_join_column_rejected(left_column, right_column):
    with pytest.raises(ValueError, match="Unknown join column"):
        optimize_join_order(
            stats("A", "B"),
            [JoinEdge("A", left_column, "B", right_column)],
        )


def test_missing_column_statistics_supported():
    data = stats("A", "B", with_columns=False)

    result = optimize_join_order(
        data,
        [JoinEdge("A", "id", "B", "id")],
    )

    assert len(result.best.order) == 2
    assert result.best.cost > 0


def test_missing_statistics_deterministic():
    data = stats("A", "B", "C", with_columns=False)
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("B", "id", "C", "id"),
    ]

    assert optimize_join_order(data, edges) == optimize_join_order(
        data,
        edges,
    )


def test_validation_does_not_mutate_inputs():
    data = stats("A", "B")
    edges = [JoinEdge("A", "id", "B", "id")]

    original_data = deepcopy(data)
    original_edges = deepcopy(edges)

    optimize_join_order(data, edges)

    assert data == original_data
    assert edges == original_edges


def test_invalid_input_does_not_mutate_inputs():
    data = stats("A", "B")
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("B", "id", "A", "id"),
    ]

    original_data = deepcopy(data)
    original_edges = deepcopy(edges)

    with pytest.raises(ValueError):
        optimize_join_order(data, edges)

    assert data == original_data
    assert edges == original_edges
