"""Tests for INTERSECT and EXCEPT."""

import pytest

from src.execution.except_operator import Except
from src.execution.intersect import Intersect
from src.execution.page_manager import SharedPageManager
from tests.test_execution_nested_loop_join import RowSource, collect

LEFT_SCHEMA = [("L.id", "int"), ("L.name", "str")]
RIGHT_SCHEMA = [("R.id", "int"), ("R.name", "str")]


def make_operation(cls, left_rows, right_rows, pages):
    return cls(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        pages,
    )


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        (Intersect, [(2, "B"), (3, "C")]),
        (Except, [(1, "A")]),
    ],
)
def test_basic_set_operations(operator, expected):
    pages = SharedPageManager(4)
    op = make_operation(
        operator,
        [(3, "C"), (1, "A"), (2, "B")],
        [(2, "B"), (4, "D"), (3, "C")],
        pages,
    )

    assert sorted(collect(op)) == expected
    assert not pages.reserved_frames


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        (Intersect, [(1, "A")]),
        (Except, [(2, "B")]),
    ],
)
def test_duplicate_elimination(operator, expected):
    pages = SharedPageManager(4)
    op = make_operation(
        operator,
        [(1, "A"), (1, "A"), (2, "B"), (2, "B")],
        [(1, "A"), (1, "A")],
        pages,
    )

    assert collect(op) == expected


@pytest.mark.parametrize(
    ("operator", "left", "right", "expected"),
    [
        (Intersect, [], [(1, "A")], []),
        (Intersect, [(1, "A")], [], []),
        (Intersect, [], [], []),
        (Except, [], [(1, "A")], []),
        (Except, [(1, "A")], [], [(1, "A")]),
        (Except, [], [], []),
    ],
)
def test_empty_relations(operator, left, right, expected):
    pages = SharedPageManager(4)
    op = make_operation(operator, left, right, pages)

    assert collect(op) == expected
    assert not pages.reserved_frames


@pytest.mark.parametrize("operator", [Intersect, Except])
def test_large_external_sort(operator):
    pages = SharedPageManager(4)
    left = [(i, f"Name_{i:04d}") for i in range(500)]
    right = [(i, f"Name_{i:04d}") for i in range(250, 750)]

    op = make_operation(operator, left, right, pages)
    result = collect(op)

    assert len(result) == 250
    assert (
        sorted(row[0] for row in result) == list(range(250, 500))
        if operator is Intersect
        else list(range(250))
    )
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames


@pytest.mark.parametrize("operator", [Intersect, Except])
def test_reopen(operator):
    pages = SharedPageManager(4)
    op = make_operation(
        operator,
        [(1, "A"), (2, "B")],
        [(1, "A")],
        pages,
    )

    first = collect(op)
    second = collect(op)

    assert first == second
    assert not pages.reserved_frames


@pytest.mark.parametrize("operator", [Intersect, Except])
def test_schema_mismatch_cleanup(operator):
    pages = SharedPageManager(4)
    op = operator(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource(
            [(1, 10)],
            [
                ("R.id", "int"),
                ("R.value", "int"),
            ],
        ),
        pages,
    )

    with pytest.raises(ValueError, match="matching column types"):
        op.open()

    assert not pages.reserved_frames


@pytest.mark.parametrize("operator", [Intersect, Except])
def test_frame_budget_during_merge(operator):
    pages = SharedPageManager(4)
    op = make_operation(
        operator,
        [(1, "A"), (2, "B"), (3, "C")],
        [(2, "B"), (3, "C")],
        pages,
    )

    op.open()
    try:
        assert len(pages.reserved_frames) == 2

        while op.next() is not None:
            assert len(pages.reserved_frames) <= 4
    finally:
        op.close()

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
