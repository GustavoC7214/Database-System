"""Tests for external sort-merge joins."""

import pytest

from src.execution.page_manager import SharedPageManager
from src.execution.sort_merge_join import SortMergeJoin
from tests.test_execution_nested_loop_join import (
    LEFT_SCHEMA,
    RIGHT_SCHEMA,
    RowSource,
    collect,
)


def test_sort_merge_join_unsorted_inputs():
    pages = SharedPageManager(4)
    op = SortMergeJoin(
        RowSource([(3, "C"), (1, "A"), (2, "B")], LEFT_SCHEMA),
        RowSource([(2, 20), (3, 30), (1, 10)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert collect(op) == [
        (1, "A", 1, 10),
        (2, "B", 2, 20),
        (3, "C", 3, 30),
    ]
    assert not pages.reserved_frames


def test_sort_merge_join_duplicate_keys():
    pages = SharedPageManager(4)
    op = SortMergeJoin(
        RowSource([(1, "B"), (1, "A")], LEFT_SCHEMA),
        RowSource([(1, 20), (1, 10)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert sorted(collect(op)) == [
        (1, "A", 1, 10),
        (1, "A", 1, 20),
        (1, "B", 1, 10),
        (1, "B", 1, 20),
    ]


@pytest.mark.parametrize(
    ("left_rows", "right_rows"),
    [
        ([], [(1, 10)]),
        ([(1, "A")], []),
        ([], []),
    ],
)
def test_sort_merge_join_empty(left_rows, right_rows):
    pages = SharedPageManager(4)
    op = SortMergeJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert collect(op) == []
    assert not pages.reserved_frames


def test_sort_merge_join_large_duplicate_group():
    pages = SharedPageManager(4)
    left = [(1, f"Employee_{i:04d}") for i in range(80)]
    right = [(1, i) for i in range(90)]

    op = SortMergeJoin(
        RowSource(left, LEFT_SCHEMA),
        RowSource(right, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    result = collect(op)

    assert len(result) == 80 * 90
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames


def test_sort_merge_join_reopen():
    pages = SharedPageManager(4)
    op = SortMergeJoin(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource([(1, 10)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert collect(op) == [(1, "A", 1, 10)]
    assert collect(op) == [(1, "A", 1, 10)]


def test_sort_merge_join_unknown_column_cleanup():
    pages = SharedPageManager(4)
    op = SortMergeJoin(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource([(1, 10)], RIGHT_SCHEMA),
        "L.missing",
        "R.id",
        pages,
    )

    with pytest.raises(ValueError, match="Unknown"):
        op.open()

    assert not pages.reserved_frames


def test_sort_merge_join_external_sort_multiple_runs():
    pages = SharedPageManager(4)

    left_rows = [(i, f"Employee_{i:05d}_" + "x" * 150) for i in range(500, 0, -1)]
    right_rows = [(i, i * 10) for i in range(500, 0, -1)]

    op = SortMergeJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    result = collect(op)

    assert len(result) == 500
    assert [row[0] for row in result] == list(range(1, 501))
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_sort_merge_join_respects_shared_frame_budget():
    pages = SharedPageManager(4)

    left_rows = [(1, f"Employee_{i:04d}") for i in range(100)]
    right_rows = [(1, i) for i in range(120)]

    op = SortMergeJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    op.open()

    try:
        assert len(pages.reserved_frames) == 3

        result = []

        while (row := op.next()) is not None:
            result.append(row)

            assert len(pages.reserved_frames) <= 4
            assert all(count == 0 for count in pages.pin_counts)

        assert len(result) == 12_000
        assert len(pages.reserved_frames) == 3

    finally:
        op.close()

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
