"""Tests for sort-based GroupBy."""

import pytest

from src.execution.group_by import GroupBy
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager


class RowSource(Operator):
    def __init__(self, rows, schema):
        super().__init__()
        self.rows = list(rows)
        self.schema = list(schema)
        self._iterator = iter(())

    def open(self) -> None:
        self._iterator = iter(self.rows)

    def next(self) -> tuple | None:
        return next(self._iterator, None)

    def close(self) -> None:
        self._iterator = iter(())


def collect(operator):
    operator.open()
    try:
        rows = []
        while (row := operator.next()) is not None:
            rows.append(row)
        return rows
    finally:
        operator.close()


SCHEMA = [
    ("R.dept", "INT"),
    ("R.salary", "INT"),
    ("R.name", "VARCHAR"),
]


def test_group_by_multiple_aggregates():
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
    )

    assert collect(op) == [
        (1, 3, 60, 20.0, "Amy", "Cal"),
        (2, 2, 80, 40.0, "Max", "Zoe"),
    ]

    assert op.schema == [
        ("R.dept", "INT"),
        ("count_star", "INT"),
        ("sum_R_salary", "INT"),
        ("avg_R_salary", "REAL"),
        ("min_R_name", "VARCHAR"),
        ("max_R_name", "VARCHAR"),
    ]
    assert op.counters()["tuples_out"] == 2
    assert not pages.reserved_frames


def test_group_by_global_aggregates():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(
            [(1, 10, "A"), (2, 20, "B")],
            SCHEMA,
        ),
        [],
        [("count", "*"), ("sum", "R.salary")],
        pages,
    )

    assert collect(op) == [(2, 30)]


def test_group_by_empty_with_keys():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource([], SCHEMA),
        ["R.dept"],
        [("count", "*")],
        pages,
    )

    assert collect(op) == []


def test_group_by_empty_global_count():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource([], SCHEMA),
        [],
        [("count", "*")],
        pages,
    )

    assert collect(op) == [(0,)]


def test_group_by_empty_global_sum_is_error():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource([], SCHEMA),
        [],
        [("sum", "R.salary")],
        pages,
    )

    with pytest.raises(ValueError, match="undefined"):
        collect(op)


def test_group_by_rejects_avg_on_string():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource([], SCHEMA),
        ["R.dept"],
        [("avg", "R.name")],
        pages,
    )

    with pytest.raises(ValueError, match="INT"):
        collect(op)


def test_group_by_reopen():
    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(
            [(1, 10, "A"), (1, 20, "B")],
            SCHEMA,
        ),
        ["R.dept"],
        [("count", "*")],
        pages,
    )

    assert collect(op) == [(1, 2)]
    assert collect(op) == [(1, 2)]
    assert not pages.reserved_frames


def test_group_by_multiple_keys():
    rows = [
        (2, 20, "B"),
        (1, 10, "A"),
        (2, 30, "A"),
        (1, 40, "B"),
        (1, 50, "A"),
        (2, 60, "B"),
    ]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept", "R.name"],
        [("count", "*"), ("sum", "R.salary")],
        pages,
    )

    assert collect(op) == [
        (1, "A", 2, 60),
        (1, "B", 1, 40),
        (2, "A", 1, 30),
        (2, "B", 2, 80),
    ]
    assert not pages.reserved_frames


def test_group_by_large_input_external_sort():
    rows = [(i % 7, i, f"Employee_{i:04d}") for i in range(1200, 0, -1)]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("count", "*"), ("sum", "R.salary")],
        pages,
    )

    result = collect(op)

    expected = [
        (
            department,
            sum(i % 7 == department for i in range(1, 1201)),
            sum(i for i in range(1, 1201) if i % 7 == department),
        )
        for department in range(7)
    ]

    assert result == expected
    assert op.counters()["page_writes"] > 0
    assert op.counters()["page_reads"] > 0
    assert not pages.reserved_frames


def test_group_by_never_exceeds_four_frames(monkeypatch):
    pages = SharedPageManager(4)
    peak = 0
    original_reserve = pages.reserve_frames

    def tracked_reserve(count):
        nonlocal peak
        indices = original_reserve(count)
        peak = max(peak, len(pages.reserved_frames))
        return indices

    monkeypatch.setattr(pages, "reserve_frames", tracked_reserve)

    rows = [(i % 5, i, f"Employee_{i:04d}") for i in range(1000, 0, -1)]

    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("count", "*")],
        pages,
    )

    assert collect(op) == [
        (0, 200),
        (1, 200),
        (2, 200),
        (3, 200),
        (4, 200),
    ]

    assert 0 < peak <= 4
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_group_by_avg_rounding():
    rows = [
        (1, 1, "A"),
        (1, 2, "B"),
        (1, 2, "C"),
        (2, 1, "D"),
        (2, 2, "E"),
        (2, 4, "F"),
    ]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("avg", "R.salary")],
        pages,
    )

    assert collect(op) == [
        (1, 1.6667),
        (2, 2.3333),
    ]
    assert not pages.reserved_frames


def test_group_by_error_releases_frames():
    rows = [
        (1, 10, "A"),
        (1, 20, 99),
        (1, 30, "C"),
    ]

    pages = SharedPageManager(4)
    op = GroupBy(
        RowSource(rows, SCHEMA),
        ["R.dept"],
        [("min", "R.name")],
        pages,
    )

    op.open()

    try:
        with pytest.raises(TypeError):
            op.next()
    finally:
        op.close()

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
