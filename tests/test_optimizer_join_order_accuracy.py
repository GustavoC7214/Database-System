"""Tests for multiple join predicates and DP table reporting."""

from copy import deepcopy

from src.optimizer.join_order import (
    JoinEdge,
    format_dp_table,
    optimize_join_order,
)
from src.optimizer.statistics import (
    ColumnStatistics,
    TableStatistics,
)


def table(name, pages=10, rows=1000, ndv=100):
    return TableStatistics(
        table=name,
        n_tuples=rows,
        n_pages=pages,
        width=40.0,
        columns={
            "id": ColumnStatistics(
                ndv=ndv,
                minimum=1,
                maximum=ndv,
            ),
            "key": ColumnStatistics(
                ndv=ndv,
                minimum=1,
                maximum=ndv,
            ),
        },
    )


def stats(*names):
    return {name: table(name) for name in names}


def conditions(plan):
    if plan["op"] == "scan":
        return []

    return conditions(plan["left"]) + conditions(plan["right"]) + [plan["condition"]]


def test_two_table_multiple_predicates():
    data = stats("A", "B")
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("A", "key", "B", "key"),
    ]

    result = optimize_join_order(data, edges)

    combined = " ".join(conditions(result.best.plan))

    assert "A.id = B.id" in combined
    assert "A.key = B.key" in combined
    assert "AND" in combined


def test_additional_predicate_reduces_estimated_rows():
    data = stats("A", "B")

    one = optimize_join_order(
        data,
        [JoinEdge("A", "id", "B", "id")],
    )

    two = optimize_join_order(
        data,
        [
            JoinEdge("A", "id", "B", "id"),
            JoinEdge("A", "key", "B", "key"),
        ],
    )

    assert two.best.rows < one.best.rows


def test_triangle_preserves_all_predicates():
    data = stats("A", "B", "C")

    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("B", "id", "C", "id"),
        JoinEdge("A", "key", "C", "key"),
    ]

    result = optimize_join_order(data, edges)

    combined = " ".join(conditions(result.best.plan))

    for edge in edges:
        assert edge.condition() in combined


def test_predicate_input_order_deterministic():
    data = stats("A", "B", "C")

    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("B", "id", "C", "id"),
        JoinEdge("A", "key", "C", "key"),
    ]

    first = optimize_join_order(data, edges)
    second = optimize_join_order(data, list(reversed(edges)))

    assert first == second


def test_multiple_predicates_do_not_mutate_inputs():
    data = stats("A", "B")
    edges = [
        JoinEdge("A", "id", "B", "id"),
        JoinEdge("A", "key", "B", "key"),
    ]

    original_data = deepcopy(data)
    original_edges = deepcopy(edges)

    optimize_join_order(data, edges)

    assert data == original_data
    assert edges == original_edges


def test_dp_table_contains_all_columns():
    result = optimize_join_order(
        stats("A", "B"),
        [JoinEdge("A", "id", "B", "id")],
    )

    output = format_dp_table(result)

    for heading in (
        "Subset",
        "Join order",
        "Rows",
        "Pages",
        "I/O cost",
    ):
        assert heading in output


def test_dp_table_contains_subsets():
    result = optimize_join_order(
        stats("A", "B", "C"),
        [
            JoinEdge("A", "id", "B", "id"),
            JoinEdge("B", "id", "C", "id"),
        ],
    )

    output = format_dp_table(result)

    assert "{A}" in output
    assert "{B}" in output
    assert "{C}" in output
    assert "{A,B}" in output
    assert "{B,C}" in output
    assert "{A,B,C}" in output


def test_dp_table_deterministic():
    result = optimize_join_order(
        stats("A", "B"),
        [JoinEdge("A", "id", "B", "id")],
    )

    assert format_dp_table(result) == format_dp_table(result)


def test_four_table_dp_table():
    data = stats("A", "B", "C", "D")

    result = optimize_join_order(
        data,
        [
            JoinEdge("A", "id", "B", "id"),
            JoinEdge("B", "id", "C", "id"),
            JoinEdge("C", "id", "D", "id"),
        ],
    )

    output = format_dp_table(result)

    assert "{A,B,C,D}" in output
    assert len(result.best.order) == 4
    assert result.best.cost > 0


def test_single_predicate_backward_compatibility():
    data = stats("A", "B")

    result = optimize_join_order(
        data,
        [JoinEdge("A", "id", "B", "id")],
    )

    assert result.best.plan["condition"] == "A.id = B.id"
