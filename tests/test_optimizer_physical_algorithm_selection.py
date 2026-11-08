"""Verify physical join algorithms against executable I/O costs."""

import pytest

from src.optimizer.cost import (
    hash_join_cost,
    nested_loop_join_cost,
    sort_merge_join_cost,
)
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.statistics import TableStatistics

SCHEMA = {
    "A": ["id", "value"],
    "B": ["id", "value"],
}


def make_stats(left_pages, right_pages):
    return {
        name: TableStatistics(
            table=name,
            n_tuples=pages * 100,
            n_pages=pages,
            width=16.0,
        )
        for name, pages in (
            ("A", left_pages),
            ("B", right_pages),
        )
    }


def join_plan():
    return {
        "op": "join",
        "condition": "A.id = B.id",
        "left": {"op": "scan", "table": "A"},
        "right": {"op": "scan", "table": "B"},
    }


def choose(left_pages, right_pages, frames=32):
    return lower_physical_plan(
        join_plan(),
        make_stats(left_pages, right_pages),
        table_columns=SCHEMA,
        frames=frames,
    )


def expected_algorithm(left_pages, right_pages, frames):
    candidates = [
        (
            nested_loop_join_cost(left_pages, right_pages, frames),
            0,
            "nested_loop_join",
        ),
        (
            hash_join_cost(left_pages, right_pages, frames),
            1,
            "hash_join",
        ),
        (
            sort_merge_join_cost(left_pages, right_pages, frames),
            2,
            "sort_merge_join",
        ),
    ]

    return min(candidates)[2]


@pytest.mark.parametrize(
    ("left_pages", "right_pages", "frames"),
    [
        (1, 1, 32),
        (10, 10, 32),
        (100, 10, 32),
        (10, 100, 32),
        (1000, 1000, 32),
        (1000, 10, 4),
        (10, 1000, 4),
        (100, 100, 8),
    ],
)
def test_algorithm_matches_executable_cost(left_pages, right_pages, frames):
    result = choose(left_pages, right_pages, frames)

    assert result["op"] == expected_algorithm(
        left_pages,
        right_pages,
        frames,
    )


def test_small_join_prefers_nested_loop():
    assert choose(1, 1)["op"] == "nested_loop_join"


def test_large_join_prefers_hash():
    assert choose(1000, 1000)["op"] == "hash_join"


def test_input_orientation_optimized():
    result = choose(100, 10)

    assert result["op"] == "nested_loop_join"
    assert result["left"]["table"] == "B"
    assert result["right"]["table"] == "A"
    assert result["left_key"] == "B.id"
    assert result["right_key"] == "A.id"


def test_algorithm_choice_is_deterministic():
    assert choose(100, 10) == choose(100, 10)
