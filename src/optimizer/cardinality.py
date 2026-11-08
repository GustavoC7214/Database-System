"""Cardinality and page-count estimates for the query optimizer."""

import math

from src.optimizer.selectivity import (
    clamp_selectivity,
    equijoin_selectivity,
)
from src.optimizer.statistics import ColumnStatistics, TableStatistics
from src.storage.disk_manager import PAGE_SIZE


def estimate_rows(
    input_rows: int,
    selectivity: float,
) -> int:
    """Estimate output rows, with a minimum of one for nonzero estimates."""
    if input_rows < 0:
        raise ValueError("Input row count cannot be negative")
    if not math.isfinite(selectivity):
        raise ValueError("Selectivity must be finite")

    if input_rows == 0:
        return 0

    selectivity = clamp_selectivity(selectivity)

    if selectivity == 0:
        return 0

    return max(1, math.ceil(input_rows * selectivity))


def estimate_pages(
    rows: int,
    width: float,
    *,
    page_size: int = PAGE_SIZE,
) -> int:
    """Estimate pages from row count and average encoded record width."""
    if rows < 0:
        raise ValueError("Row count cannot be negative")
    if not math.isfinite(width) or width < 0:
        raise ValueError("Record width must be finite and nonnegative")
    if page_size < 1:
        raise ValueError("Page size must be positive")

    if rows == 0:
        return 0

    return max(1, math.ceil(rows * width / page_size))


def estimate_filter(
    statistics: TableStatistics,
    selectivity: float,
) -> tuple[int, int]:
    """Estimate (rows, pages) after a filter."""
    rows = estimate_rows(statistics.n_tuples, selectivity)
    pages = estimate_pages(rows, statistics.width)
    return rows, pages


def estimate_join_rows(
    left_rows: int,
    right_rows: int,
    left_column: ColumnStatistics | None,
    right_column: ColumnStatistics | None,
) -> int:
    """Estimate rows for an equality join."""
    if left_rows < 0 or right_rows < 0:
        raise ValueError("Join input cardinalities cannot be negative")

    if left_rows == 0 or right_rows == 0:
        return 0

    selectivity = equijoin_selectivity(
        left_column,
        right_column,
    )

    return estimate_rows(
        left_rows * right_rows,
        selectivity,
    )


def estimate_join_pages(
    rows: int,
    left_width: float,
    right_width: float,
) -> int:
    """Estimate pages occupied by concatenated join rows."""
    return estimate_pages(rows, left_width + right_width)
