"""Tests for optimizer cardinality and page estimation."""

import pytest

from src.optimizer.cardinality import (
    estimate_filter,
    estimate_join_pages,
    estimate_join_rows,
    estimate_pages,
    estimate_rows,
)
from src.optimizer.statistics import ColumnStatistics, TableStatistics


def test_estimate_rows():
    assert estimate_rows(100, 0.25) == 25
    assert estimate_rows(6, 0.2) == 2


def test_estimate_rows_minimum_one():
    assert estimate_rows(100, 0.001) == 1


def test_zero_selectivity():
    assert estimate_rows(100, 0) == 0


def test_empty_input():
    assert estimate_rows(0, 0.5) == 0


def test_estimate_pages():
    assert estimate_pages(1000, 16) == 4


def test_estimate_pages_rounding():
    assert estimate_pages(1, 20) == 1
    assert estimate_pages(0, 20) == 0


def test_estimate_filter():
    stats = TableStatistics(
        table="Emp",
        n_tuples=1000,
        n_pages=4,
        width=16,
    )

    rows, pages = estimate_filter(stats, 0.25)

    assert rows == 250
    assert pages == 1


def test_estimate_join_rows():
    left = ColumnStatistics(50, 1, 50)
    right = ColumnStatistics(50, 1, 50)

    assert estimate_join_rows(10000, 50, left, right) == 10000


def test_estimate_join_pages():
    assert estimate_join_pages(1000, 16, 16) == 8


def test_join_empty_input():
    left = ColumnStatistics(5, 1, 5)
    right = ColumnStatistics(5, 1, 5)

    assert estimate_join_rows(0, 100, left, right) == 0


def test_invalid_row_count():
    with pytest.raises(ValueError):
        estimate_rows(-1, 0.5)


def test_invalid_page_width():
    with pytest.raises(ValueError):
        estimate_pages(100, -1)
