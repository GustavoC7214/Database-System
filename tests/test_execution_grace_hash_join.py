"""Tests for Grace hash equijoins."""

import pytest

from src.execution.grace_hash_join import GraceHashJoin
from src.execution.page_manager import SharedPageManager
from tests.test_execution_nested_loop_join import (
    LEFT_SCHEMA,
    RIGHT_SCHEMA,
    RowSource,
    collect,
)


def make_join(left_rows, right_rows, pages):
    return GraceHashJoin(
        RowSource(left_rows, LEFT_SCHEMA),
        RowSource(right_rows, RIGHT_SCHEMA),
        "L.id",
        "R.id",
        pages,
    )


def test_grace_hash_join_basic():
    pages = SharedPageManager(4)
    op = make_join(
        [(3, "C"), (1, "A"), (2, "B")],
        [(2, 20), (1, 10), (4, 40)],
        pages,
    )

    assert sorted(collect(op)) == [
        (1, "A", 1, 10),
        (2, "B", 2, 20),
    ]
    assert not pages.reserved_frames


def test_grace_hash_join_duplicates():
    pages = SharedPageManager(4)
    op = make_join(
        [(1, "A"), (1, "B")],
        [(1, 10), (1, 20)],
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
def test_grace_hash_join_empty(left_rows, right_rows):
    pages = SharedPageManager(4)
    op = make_join(left_rows, right_rows, pages)

    assert collect(op) == []
    assert not pages.reserved_frames


def test_grace_hash_join_many_partitions():
    pages = SharedPageManager(4)
    left = [(i, f"Employee_{i:04d}") for i in range(250)]
    right = [(i, i * 10) for i in range(250)]

    op = make_join(left, right, pages)
    result = collect(op)

    assert len(result) == 250
    assert sorted(row[0] for row in result) == list(range(250))
    assert op.counters()["page_reads"] > 0
    assert op.counters()["page_writes"] > 0
    assert not pages.reserved_frames


def test_grace_hash_join_skewed_overflow():
    pages = SharedPageManager(4)

    # All rows have the same key, forcing one large partition.
    left = [(1, f"Employee_{i:04d}") for i in range(150)]
    right = [(1, i) for i in range(100)]

    op = make_join(left, right, pages)
    result = collect(op)

    assert len(result) == 15_000
    assert op.counters()["page_reads"] > 0
    assert op.counters()["comparisons"] > 0
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_grace_hash_join_reopen():
    pages = SharedPageManager(4)
    op = make_join([(1, "A")], [(1, 10)], pages)

    assert collect(op) == [(1, "A", 1, 10)]
    assert collect(op) == [(1, "A", 1, 10)]


def test_grace_hash_join_invalid_key_cleanup():
    pages = SharedPageManager(4)
    op = GraceHashJoin(
        RowSource([(1, "A")], LEFT_SCHEMA),
        RowSource([(1, 10)], RIGHT_SCHEMA),
        "L.missing",
        "R.id",
        pages,
    )

    with pytest.raises(ValueError, match="Unknown"):
        op.open()

    assert not pages.reserved_frames


def test_grace_hash_join_uses_fallback(monkeypatch):
    pages = SharedPageManager(4)
    left = [(1, f"Employee_{i:04d}") for i in range(150)]
    right = [(1, i) for i in range(20)]

    calls = []
    original = GraceHashJoin._fallback

    def tracked_fallback(self, left_path, right_path):
        calls.append((left_path, right_path))
        yield from original(self, left_path, right_path)

    monkeypatch.setattr(GraceHashJoin, "_fallback", tracked_fallback)

    op = make_join(left, right, pages)

    assert len(collect(op)) == 3_000
    assert len(calls) >= 1
    assert not pages.reserved_frames
