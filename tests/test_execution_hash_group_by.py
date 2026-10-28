"""Regression tests for hash-based GroupBy."""

from unittest.mock import patch

import pytest

from src.execution.group_by import GroupBy
from src.execution.hash_group_by import HashGroupBy
from src.execution.page_manager import SharedPageManager
from tests.test_execution_group_by import SCHEMA, RowSource, collect


def test_hash_group_by_multiple_aggregates():
    rows = [
        (2, 30, "Zoe"),
        (1, 10, "Amy"),
        (2, 50, "Max"),
        (1, 20, "Bob"),
        (1, 30, "Cal"),
    ]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [
            ("count", "*"),
            ("sum", "R.salary"),
            ("avg", "R.salary"),
            ("min", "R.name"),
            ("max", "R.name"),
        ],
        pages,
        mode="hash",
    )

    assert sorted(collect(op)) == [
        (1, 3, 60, 20.0, "Amy", "Cal"),
        (2, 2, 80, 40.0, "Max", "Zoe"),
    ]
    assert not pages.reserved_frames


def test_hash_group_by_multiple_keys():
    rows = [
        (1, 10, "A"),
        (2, 20, "B"),
        (1, 30, "A"),
        (2, 40, "B"),
        (1, 50, "B"),
    ]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept", "R.name"],
        [("count", "*"), ("sum", "R.salary")],
        pages,
        mode="hash",
    )

    assert sorted(collect(op)) == [
        (1, "A", 2, 40),
        (1, "B", 1, 50),
        (2, "B", 2, 60),
    ]


def test_hash_group_by_global_aggregation():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(
            [(1, 10, "A"), (2, 20, "B")],
            SCHEMA,
        ),
        [],
        [("count", "*"), ("sum", "R.salary")],
        pages,
        mode="hash",
    )

    assert collect(op) == [(2, 30)]


def test_hash_group_by_empty_inputs():
    pages = SharedPageManager(4)

    grouped = GroupBy(
        RowSource([], SCHEMA),
        ["R.dept"],
        [("count", "*")],
        pages,
        mode="hash",
    )
    assert collect(grouped) == []

    global_count = GroupBy(
        RowSource([], SCHEMA),
        [],
        [("count", "*")],
        pages,
        mode="hash",
    )
    assert collect(global_count) == [(0,)]

    global_sum = GroupBy(
        RowSource([], SCHEMA),
        [],
        [("sum", "R.salary")],
        pages,
        mode="hash",
    )
    with pytest.raises(ValueError, match="undefined"):
        collect(global_sum)

    assert not pages.reserved_frames


def test_hash_group_by_partition_overflow():
    # Many distinct groups force at least one partition
    # to exceed the logical B-2-page aggregation allowance.
    rows = [(i, i * 2, f"Employee_{i:04d}") for i in range(600, 0, -1)]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("count", "*"), ("sum", "R.salary")],
        pages,
        mode="hash",
    )

    result = collect(op)

    assert sorted(result) == [(i, 1, i * 2) for i in range(1, 601)]
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_hash_group_by_reopen():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(
            [(1, 10, "A"), (1, 20, "B")],
            SCHEMA,
        ),
        ["R.dept"],
        [("count", "*")],
        pages,
        mode="hash",
    )

    assert collect(op) == [(1, 2)]
    assert collect(op) == [(1, 2)]
    assert not pages.reserved_frames


def test_hash_group_by_invalid_aggregate_cleanup():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(
            [(1, 10, "A"), (1, 20, 99)],
            SCHEMA,
        ),
        ["R.dept"],
        [("min", "R.name")],
        pages,
        mode="hash",
    )

    op.open()
    try:
        with pytest.raises(TypeError):
            while op.next() is not None:
                pass
    finally:
        op.close()

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_hash_group_by_overflow_uses_sort_fallback():
    rows = [(i, i * 2, f"Employee_{i:04d}") for i in range(600, 0, -1)]

    pages = SharedPageManager(4)

    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("count", "*"), ("sum", "R.salary")],
        pages,
        mode="hash",
    )

    original_fallback = HashGroupBy._fallback

    with patch.object(
        HashGroupBy,
        "_fallback",
        autospec=True,
        side_effect=original_fallback,
    ) as fallback:
        result = collect(op)

        assert fallback.call_count >= 1

    assert sorted(result) == [(i, 1, i * 2) for i in range(1, 601)]

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
