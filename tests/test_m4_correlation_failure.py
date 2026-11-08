"""Regression tests for the M4 correlated-cardinality experiment."""

from collections import Counter
from unittest.mock import patch

import pytest

from experiments.m4.benchmark_correlation_failure import (
    ACTUAL_FILTERED_ROWS,
    COLUMNS,
    FILTER,
    TABLES,
    corrected_estimator,
    logical_plan,
)
from experiments.m4.generate_correlated_dataset import generate_correlated_dataset
from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.analyze import analyze_table
from src.optimizer.cardinality import estimate_pages
from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.statistics import StatisticsStore


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """Generate an isolated correlated database for the test module."""
    db_dir = tmp_path_factory.mktemp("m4_correlated") / "db"

    counts = generate_correlated_dataset(db_dir)

    assert counts == {
        "CorrelatedCustomers": 25_000,
        "CorrelatedOrders": 6_000,
    }

    return db_dir


@pytest.fixture(scope="module")
def statistics(db):
    """Generate and load optimizer statistics for both tables."""
    store = StatisticsStore(db)

    for table in TABLES:
        analyze_table(db, table, frames=8)

    stats = {table: store.load(table) for table in TABLES}

    assert all(value is not None for value in stats.values())

    return stats


def build_plans(statistics, frames):
    logical = logical_plan()

    original = lower_physical_plan(
        logical,
        statistics,
        table_columns=COLUMNS,
        frames=frames,
    )

    original_method = LogicalPlanEstimator.estimate

    with patch.object(
        LogicalPlanEstimator,
        "estimate",
        corrected_estimator(original_method),
    ):
        corrected = lower_physical_plan(
            logical,
            statistics,
            table_columns=COLUMNS,
            frames=frames,
        )

    return original, corrected


def test_correlated_selection_underestimation(statistics):
    estimator = LogicalPlanEstimator(
        statistics,
        table_columns=COLUMNS,
    )

    filtered = logical_plan()["left"]
    estimate = estimator.estimate(filtered)

    assert filtered["condition"] == FILTER
    assert estimate.rows == 251
    assert ACTUAL_FILTERED_ROWS == 2500
    assert estimate.pages == 1
    assert estimate_pages(ACTUAL_FILTERED_ROWS, estimate.width) == 10


def test_corrected_cardinality_changes_four_frame_algorithm(statistics):
    original, corrected = build_plans(statistics, frames=4)

    assert original["op"] == "nested_loop_join"
    assert corrected["op"] == "hash_join"


@pytest.mark.parametrize("frames", [4, 8, 16, 32])
def test_original_and_corrected_plans_return_identical_rows(
    statistics,
    db,
    frames,
):
    original, corrected = build_plans(statistics, frames)

    original_result = PhysicalPlanExecutor(
        db,
        frames=frames,
    ).execute(original)

    corrected_result = PhysicalPlanExecutor(
        db,
        frames=frames,
    ).execute(corrected)

    assert Counter(original_result.rows) == Counter(corrected_result.rows)
    assert len(original_result.rows) == 600
    assert len(corrected_result.rows) == 600


def test_corrected_plan_reduces_four_frame_buffer_reads(statistics, db):
    original, corrected = build_plans(statistics, frames=4)

    original_result = PhysicalPlanExecutor(
        db,
        frames=4,
    ).execute(original)

    corrected_result = PhysicalPlanExecutor(
        db,
        frames=4,
    ).execute(corrected)

    assert original_result.buffer_stats is not None
    assert corrected_result.buffer_stats is not None

    assert (
        corrected_result.buffer_stats["reads"] < original_result.buffer_stats["reads"]
    )

    assert original_result.buffer_stats["writes"] == 0
    assert corrected_result.buffer_stats["writes"] == 0
