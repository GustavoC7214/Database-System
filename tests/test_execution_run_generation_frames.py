"""Tests for shared-frame accounting during run generation."""

import tempfile
from pathlib import Path

import pytest

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.run_generation import generate_sorted_runs


class RowSource(Operator):
    def __init__(self, rows):
        super().__init__()
        self.rows = list(rows)
        self._iterator = iter(self.rows)

    def open(self) -> None:
        self._iterator = iter(self.rows)

    def next(self) -> tuple | None:
        return next(self._iterator, None)

    def close(self) -> None:
        pass


def test_run_generation_reserves_shared_frames(monkeypatch):
    pages = SharedPageManager(4)
    reservations = []

    original_reserve = pages.reserve_frames

    def tracked_reserve(count):
        result = original_reserve(count)
        reservations.append(len(pages.reserved_frames))
        return result

    monkeypatch.setattr(pages, "reserve_frames", tracked_reserve)

    rows = [(i, "x" * 150) for i in range(300)]

    with tempfile.TemporaryDirectory() as directory:
        runs = generate_sorted_runs(
            RowSource(rows),
            4,
            lambda row: row[0],
            Path(directory),
            pages=pages,
        )

        assert len(runs) > 1

    assert reservations
    assert max(reservations) == 3
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_run_generation_releases_frames_on_failure():
    pages = SharedPageManager(4)

    # A tuple larger than a temporary page must raise an error.
    rows = [(1, "x" * 5000)]

    with (
        tempfile.TemporaryDirectory() as directory,
        pytest.raises(ValueError, match="capacity"),
    ):
        generate_sorted_runs(
            RowSource(rows),
            4,
            lambda row: row[0],
            Path(directory),
            pages=pages,
        )

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_run_generation_releases_frames_after_sort_key_failure():
    pages = SharedPageManager(4)

    def failing_key(row):
        raise RuntimeError("Sort key failure")

    with (
        tempfile.TemporaryDirectory() as directory,
        pytest.raises(RuntimeError, match="Sort key failure"),
    ):
        generate_sorted_runs(
            RowSource([(1, "a"), (2, "b")]),
            4,
            failing_key,
            Path(directory),
            pages=pages,
        )

    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
