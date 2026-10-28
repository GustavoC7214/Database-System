"""Tests for block nested-loop joins."""

from collections.abc import Sequence

import pytest

from src.execution.nested_loop_join import NestedLoopJoin
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager

Row = tuple[int | str | float, ...]


class RowSource(Operator):
    def __init__(
        self,
        rows: Sequence[Row],
        schema: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.rows = rows
        self.schema = schema
        self.position = 0
        self.opened = False

    def open(self) -> None:
        self.position = 0
        self.opened = True

    def next(self) -> Row | None:
        if not self.opened:
            raise RuntimeError("Source is not open")
        if self.position >= len(self.rows):
            return None
        row = self.rows[self.position]
        self.position += 1
        return row

    def close(self) -> None:
        self.opened = False


LEFT_SCHEMA = [("L.id", "INT"), ("L.name", "VARCHAR")]
RIGHT_SCHEMA = [("R.id", "INT"), ("R.value", "INT")]


def collect(op: Operator) -> list[Row]:
    op.open()
    try:
        result = []
        while (row := op.next()) is not None:
            result.append(row)
        return result
    finally:
        op.close()


def test_nested_loop_join_basic():
    pages = SharedPageManager(4)
    op = NestedLoopJoin(
        RowSource([(1, "A"), (2, "B"), (3, "C")], LEFT_SCHEMA),
        RowSource([(2, 20), (3, 30), (4, 40)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert sorted(collect(op)) == [
        (2, "B", 2, 20),
        (3, "C", 3, 30),
    ]
    assert op.schema == LEFT_SCHEMA + RIGHT_SCHEMA
    assert not pages.reserved_frames


def test_nested_loop_join_duplicate_keys():
    pages = SharedPageManager(4)
    op = NestedLoopJoin(
        RowSource([(1, "A"), (1, "B")], LEFT_SCHEMA),
        RowSource([(1, 10), (1, 20)], RIGHT_SCHEMA),
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
def test_nested_loop_join_empty(left_rows, right_rows):
    pages = SharedPageManager(4)
    op = NestedLoopJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )
    assert collect(op) == []
    assert not pages.reserved_frames


def test_nested_loop_join_many_outer_blocks():
    pages = SharedPageManager(4)
    left_rows = [(i, f"Name_{i:04d}_" + "x" * 150) for i in range(250)]
    right_rows = [(i, i * 10) for i in range(250)]

    op = NestedLoopJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    result = collect(op)

    assert len(result) == 250
    assert sorted(row[0] for row in result) == list(range(250))
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_nested_loop_join_reopen():
    pages = SharedPageManager(4)
    op = NestedLoopJoin(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource([(1, 10)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    assert collect(op) == [(1, "A", 1, 10)]
    assert collect(op) == [(1, "A", 1, 10)]


def test_nested_loop_join_unknown_key_cleanup():
    pages = SharedPageManager(4)
    op = NestedLoopJoin(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource([(1, 10)], RIGHT_SCHEMA),
        "L.missing",
        "R.id",
        pages,
    )

    with pytest.raises(ValueError, match="Unknown"):
        op.open()

    assert not pages.reserved_frames


@pytest.mark.parametrize(
    ("frames", "expected_reserved"),
    [
        (4, 3),
        (16, 15),
        (64, 63),
    ],
)
def test_nested_loop_join_scales_frame_reservations(
    frames,
    expected_reserved,
):
    pages = SharedPageManager(frames)

    op = NestedLoopJoin(
        RowSource([(1, "A"), (2, "B")], LEFT_SCHEMA),
        RowSource([(1, 10), (2, 20)], RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )

    op.open()

    try:
        assert len(pages.reserved_frames) == expected_reserved

        rows = []
        while (row := op.next()) is not None:
            rows.append(row)

        assert sorted(rows) == [
            (1, "A", 1, 10),
            (2, "B", 2, 20),
        ]
    finally:
        op.close()

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_nested_loop_join_more_memory_reduces_rescans():
    left_rows = [(i, f"Name_{i:04d}_" + "x" * 150) for i in range(250)]
    right_rows = [(i, i * 10) for i in range(250)]

    results = {}

    for frames in (4, 16):
        pages = SharedPageManager(frames)

        op = NestedLoopJoin(
            RowSource(left_rows, LEFT_SCHEMA),
            RowSource(right_rows, RIGHT_SCHEMA),
            "L.id",
            "R.id",
            pages,
        )

        rows = collect(op)

        assert len(rows) == 250
        assert not pages.reserved_frames
        assert all(count == 0 for count in pages.pin_counts)

        results[frames] = op.counters()["page_reads"]

    assert results[16] < results[4]
