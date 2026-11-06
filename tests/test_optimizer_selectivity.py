"""Tests for optimizer selectivity estimation."""

import pytest

from src.optimizer.selectivity import (
    and_selectivity,
    comparison_selectivity,
    equality_selectivity,
    equijoin_selectivity,
    not_selectivity,
    or_selectivity,
    range_selectivity,
)
from src.optimizer.statistics import (
    ColumnStatistics,
    HistogramBucket,
)


def make_age_stats():
    return ColumnStatistics(
        ndv=5,
        minimum=20,
        maximum=60,
        histogram=(
            HistogramBucket(20, 30, 2, 2),
            HistogramBucket(30, 40, 2, 2),
            HistogramBucket(50, 60, 2, 2),
        ),
    )


def test_equality_from_histogram():
    assert equality_selectivity(make_age_stats(), 30, n_tuples=6) == pytest.approx(
        1 / 3
    )


def test_equality_outside_range():
    assert equality_selectivity(make_age_stats(), 100) == 0


def test_equality_without_histogram():
    column = ColumnStatistics(5, 20, 60)
    assert equality_selectivity(column, 30) == pytest.approx(0.2)


def test_equality_missing_statistics():
    assert equality_selectivity(None, 30) == pytest.approx(0.1)


def test_not_equal():
    result = comparison_selectivity(make_age_stats(), "!=", 30, n_tuples=6)
    assert result == pytest.approx(2 / 3)


def test_less_than_range():
    result = range_selectivity(make_age_stats(), "<", 40)
    assert 0 < result < 1


def test_greater_than_range():
    result = range_selectivity(make_age_stats(), ">", 40)
    assert 0 < result < 1


def test_range_outside_domain():
    column = ColumnStatistics(5, 20, 60)
    assert range_selectivity(column, "<", 10) == 0
    assert range_selectivity(column, ">", 70) == 0


def test_range_without_histogram():
    column = ColumnStatistics(5, 20, 60)
    assert range_selectivity(column, "<", 40) == pytest.approx(0.5)


def test_missing_range_statistics():
    assert range_selectivity(None, "<", 40) == pytest.approx(1 / 3)


def test_boolean_and():
    assert and_selectivity(0.5, 0.2) == pytest.approx(0.1)


def test_boolean_or():
    assert or_selectivity(0.5, 0.2) == pytest.approx(0.6)


def test_boolean_not():
    assert not_selectivity(0.3) == pytest.approx(0.7)


def test_equijoin_ndv():
    left = ColumnStatistics(50, 1, 50)
    right = ColumnStatistics(20, 1, 20)

    assert equijoin_selectivity(left, right) == pytest.approx(1 / 50)


def test_equijoin_disjoint_ranges():
    left = ColumnStatistics(10, 1, 10)
    right = ColumnStatistics(10, 20, 30)

    assert equijoin_selectivity(left, right) == 0


def test_equijoin_missing_statistics():
    assert equijoin_selectivity(None, None) == pytest.approx(0.1)


def test_empty_column():
    empty = ColumnStatistics(0, None, None)

    assert equality_selectivity(empty, 5) == 0
    assert range_selectivity(empty, "<", 5) == 0


def test_invalid_range_operator():
    with pytest.raises(ValueError, match="Unsupported"):
        range_selectivity(make_age_stats(), "LIKE", 30)
