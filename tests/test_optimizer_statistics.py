"""Tests for persistent optimizer statistics."""

import json

import pytest

from src.optimizer.statistics import (
    ColumnStatistics,
    HistogramBucket,
    StatisticsStore,
    TableStatistics,
)


def make_statistics() -> TableStatistics:
    return TableStatistics(
        table="Emp",
        n_tuples=100,
        n_pages=2,
        width=12.5,
        columns={
            "age": ColumnStatistics(
                ndv=4,
                minimum=20,
                maximum=50,
                histogram=(
                    HistogramBucket(
                        lower=20,
                        upper=30,
                        count=50,
                        ndv=2,
                    ),
                    HistogramBucket(
                        lower=40,
                        upper=50,
                        count=50,
                        ndv=2,
                    ),
                ),
            ),
            "name": ColumnStatistics(
                ndv=2,
                minimum="Alice",
                maximum="Bob",
                histogram=(
                    HistogramBucket(
                        lower="Alice",
                        upper="Bob",
                        count=100,
                        ndv=2,
                    ),
                ),
            ),
        },
    )


def test_statistics_round_trip(tmp_path):
    store = StatisticsStore(tmp_path)
    original = make_statistics()

    store.save(original)

    assert store.load("Emp") == original


def test_missing_statistics_returns_none(tmp_path):
    store = StatisticsStore(tmp_path)

    assert store.load("Unknown") is None


def test_save_twice_produces_identical_bytes(tmp_path):
    store = StatisticsStore(tmp_path)
    statistics = make_statistics()

    store.save(statistics)

    path = tmp_path / "optimizer_stats" / "Emp.json"
    first = path.read_bytes()

    store.save(statistics)
    second = path.read_bytes()

    assert first == second


def test_save_replaces_previous_statistics(tmp_path):
    store = StatisticsStore(tmp_path)
    original = make_statistics()

    store.save(original)

    updated = TableStatistics(
        table="Emp",
        n_tuples=0,
        n_pages=2,
        width=0.0,
        columns={
            "age": ColumnStatistics(
                ndv=0,
                minimum=None,
                maximum=None,
            ),
        },
    )

    store.save(updated)

    assert store.load("Emp") == updated


def test_statistics_are_valid_json(tmp_path):
    store = StatisticsStore(tmp_path)
    store.save(make_statistics())

    path = tmp_path / "optimizer_stats" / "Emp.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["n_tuples"] == 100
    assert payload["columns"]["age"]["ndv"] == 4
    assert len(payload["columns"]["age"]["histogram"]) == 2


def test_delete_statistics(tmp_path):
    store = StatisticsStore(tmp_path)
    store.save(make_statistics())

    store.delete("Emp")

    assert store.load("Emp") is None


def test_invalid_histogram_bucket():
    with pytest.raises(ValueError):
        HistogramBucket(
            lower=10,
            upper=20,
            count=5,
            ndv=6,
        )


def test_invalid_histogram_boundaries():
    with pytest.raises(ValueError):
        HistogramBucket(
            lower=30,
            upper=10,
            count=5,
            ndv=2,
        )


def test_invalid_table_statistics():
    with pytest.raises(ValueError):
        TableStatistics(
            table="Emp",
            n_tuples=-1,
            n_pages=1,
            width=10,
        )


def test_invalid_table_name(tmp_path):
    store = StatisticsStore(tmp_path)

    with pytest.raises(ValueError):
        store.load("../outside")


def test_unsupported_statistics_version(tmp_path):
    store = StatisticsStore(tmp_path)
    store.save(make_statistics())

    path = tmp_path / "optimizer_stats" / "Emp.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = 999

    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported statistics version"):
        store.load("Emp")
