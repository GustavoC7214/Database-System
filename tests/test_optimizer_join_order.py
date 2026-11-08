"""Tests for Selinger-style left-deep join ordering."""

from copy import deepcopy
from itertools import pairwise

import pytest

from src.optimizer.join_order import (
    JoinEdge,
    optimize_join_order,
)
from src.optimizer.statistics import TableStatistics


def table(name, pages, rows=None):
    return TableStatistics(
        table=name,
        n_tuples=rows if rows is not None else pages * 100,
        n_pages=pages,
        width=40.0,
    )


def chain_edges(*names):
    return [JoinEdge(left, "id", right, "id") for left, right in pairwise(names)]


def walk(plan):
    yield plan
    if "left" in plan:
        yield from walk(plan["left"])
    if "right" in plan:
        yield from walk(plan["right"])


def test_two_table_join():
    stats = {"A": table("A", 100), "B": table("B", 10)}
    result = optimize_join_order(
        stats,
        [JoinEdge("A", "id", "B", "id")],
    )

    assert set(result.best.order) == {"A", "B"}
    assert result.best.plan["op"] == "join"
    assert len(result.entries) == 3


def test_three_table_chain():
    stats = {
        "A": table("A", 100),
        "B": table("B", 10),
        "C": table("C", 400),
    }
    result = optimize_join_order(
        stats,
        chain_edges("A", "B", "C"),
    )

    assert set(result.best.order) == {"A", "B", "C"}
    assert len(result.best.order) == 3
    assert result.best.cost > 0


def test_left_deep_shape():
    stats = {
        name: table(name, pages)
        for name, pages in [
            ("A", 100),
            ("B", 10),
            ("C", 400),
            ("D", 50),
        ]
    }
    result = optimize_join_order(
        stats,
        chain_edges("A", "B", "C", "D"),
    )

    plan = result.best.plan

    while plan["op"] == "join":
        assert plan["right"]["op"] == "scan"
        plan = plan["left"]

    assert plan["op"] == "scan"


def test_no_cartesian_joins():
    stats = {
        "A": table("A", 100),
        "B": table("B", 10),
        "C": table("C", 400),
    }
    result = optimize_join_order(
        stats,
        chain_edges("A", "B", "C"),
    )

    assert all(node["op"] != "cross" for node in walk(result.best.plan))


def test_all_tables_appear_once():
    stats = {name: table(name, 10) for name in "ABCDE"}
    result = optimize_join_order(
        stats,
        chain_edges(*stats),
    )

    scans = [node["table"] for node in walk(result.best.plan) if node["op"] == "scan"]

    assert sorted(scans) == sorted(stats)


def test_dp_entries_cover_singletons():
    stats = {
        "A": table("A", 10),
        "B": table("B", 20),
        "C": table("C", 30),
    }
    result = optimize_join_order(
        stats,
        chain_edges("A", "B", "C"),
    )

    singletons = [entry for entry in result.entries if len(entry.tables) == 1]

    assert len(singletons) == 3


def test_dp_entries_unique_per_subset():
    stats = {name: table(name, 10) for name in "ABCD"}
    result = optimize_join_order(
        stats,
        chain_edges(*stats),
    )

    subsets = [entry.tables for entry in result.entries]

    assert len(subsets) == len(set(subsets))


def test_deterministic_result():
    stats = {
        "A": table("A", 100),
        "B": table("B", 10),
        "C": table("C", 400),
    }
    edges = chain_edges("A", "B", "C")

    first = optimize_join_order(stats, edges)
    second = optimize_join_order(stats, edges)

    assert first == second


def test_input_order_does_not_change_result():
    stats = {
        "C": table("C", 400),
        "A": table("A", 100),
        "B": table("B", 10),
    }
    edges = chain_edges("A", "B", "C")

    first = optimize_join_order(stats, edges)
    second = optimize_join_order(
        dict(reversed(list(stats.items()))),
        list(reversed(edges)),
    )

    assert first == second


def test_does_not_mutate_inputs():
    stats = {
        "A": table("A", 100),
        "B": table("B", 10),
    }
    edges = chain_edges("A", "B")

    original_stats = deepcopy(stats)
    original_edges = deepcopy(edges)

    optimize_join_order(stats, edges)

    assert stats == original_stats
    assert edges == original_edges


def test_six_table_limit_supported():
    stats = {name: table(name, 10) for name in "ABCDEF"}
    result = optimize_join_order(
        stats,
        chain_edges(*stats),
    )

    assert len(result.best.order) == 6


def test_disconnected_graph_rejected():
    stats = {name: table(name, 10) for name in "ABC"}

    with pytest.raises(ValueError, match="disconnected"):
        optimize_join_order(
            stats,
            [JoinEdge("A", "id", "B", "id")],
        )


def test_unknown_table_rejected():
    stats = {
        "A": table("A", 10),
        "B": table("B", 10),
    }

    with pytest.raises(ValueError, match="unknown table"):
        optimize_join_order(
            stats,
            [JoinEdge("A", "id", "Z", "id")],
        )


@pytest.mark.parametrize("count", [0, 1, 7])
def test_invalid_table_count(count):
    stats = {f"T{index}": table(f"T{index}", 10) for index in range(count)}

    with pytest.raises(ValueError, match="2 to 6"):
        optimize_join_order(
            stats,
            [JoinEdge("A", "id", "B", "id")],
        )


@pytest.mark.parametrize("frames", [0, 1, 2])
def test_insufficient_frames(frames):
    stats = {
        "A": table("A", 10),
        "B": table("B", 10),
    }

    with pytest.raises(ValueError):
        optimize_join_order(
            stats,
            chain_edges("A", "B"),
            frames=frames,
        )


def test_invalid_join_edge():
    with pytest.raises(ValueError):
        JoinEdge("A", "id", "A", "id")


def test_missing_edges_rejected():
    stats = {
        "A": table("A", 10),
        "B": table("B", 10),
    }

    with pytest.raises(ValueError, match="predicate"):
        optimize_join_order(stats, [])


def test_assignment_three_relation_worked_example():
    """Reproduce the Module 4 worked example: 530 page I/Os."""

    from src.optimizer.statistics import ColumnStatistics

    def column(ndv):
        return ColumnStatistics(
            ndv=ndv,
            minimum=1,
            maximum=ndv,
        )

    # The assignment specifies intermediate results of:
    # A JOIN B: 1000 rows, 20 pages
    # B JOIN C: 2000 rows, 40 pages
    #
    # These widths and NDVs reproduce those estimates using
    # the project's cardinality and page-estimation formulas.
    statistics = {
        "A": TableStatistics(
            table="A",
            n_tuples=5000,
            n_pages=100,
            width=40.96,
            columns={"x": column(2500)},
        ),
        "B": TableStatistics(
            table="B",
            n_tuples=500,
            n_pages=10,
            width=40.96,
            columns={
                "x": column(500),
                "y": column(500),
            },
        ),
        "C": TableStatistics(
            table="C",
            n_tuples=20000,
            n_pages=400,
            width=40.96,
            columns={"y": column(5000)},
        ),
    }

    edges = [
        JoinEdge("A", "x", "B", "x"),
        JoinEdge("B", "y", "C", "y"),
    ]

    result = optimize_join_order(
        statistics,
        edges,
        frames=32,
    )

    entries = {entry.tables: entry for entry in result.entries}

    ab = entries[frozenset({"A", "B"})]
    bc = entries[frozenset({"B", "C"})]

    assert ab.rows == 1000
    assert ab.pages == 20
    assert ab.cost == 110

    assert bc.rows == 2000
    assert bc.pages == 40
    assert bc.cost == 410

    # A and C have no direct join predicate.
    assert frozenset({"A", "C"}) not in entries

    assert result.best.order == ("B", "A", "C")
    assert result.best.cost == 530


def test_intermediate_join_uses_left_deep_executable_cost():
    """An intermediate join cannot reverse its nested-loop inputs."""
    from src.optimizer.cost import (
        hash_join_cost,
        nested_loop_join_cost,
        sort_merge_join_cost,
    )
    from src.optimizer.join_order import _join_algorithm

    frames = 32
    intermediate_pages = 400
    base_pages = 10

    reversed_cost = nested_loop_join_cost(base_pages, intermediate_pages, frames)
    left_deep_cost = nested_loop_join_cost(intermediate_pages, base_pages, frames)

    assert reversed_cost < left_deep_cost

    algorithm, cost = _join_algorithm(
        intermediate_pages,
        base_pages,
        frames,
        allow_swap=False,
    )

    assert cost == min(
        left_deep_cost,
        hash_join_cost(intermediate_pages, base_pages, frames),
        sort_merge_join_cost(intermediate_pages, base_pages, frames),
    )
    assert algorithm != "nested_loop_join:right"
