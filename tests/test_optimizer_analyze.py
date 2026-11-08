"""Tests for Module 4 ANALYZE and equi-depth histograms."""

import json

import pytest

from src.optimizer.analyze import analyze_table
from src.optimizer.cli import main
from src.optimizer.histogram import build_column_statistics
from src.optimizer.statistics import StatisticsStore
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def create_employee_table(tmp_path, rows):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "Emp",
        "id:INT,age:INT,name:VARCHAR(30)",
    )

    heap = HeapFile(tmp_path / metadata.filename)

    rids = []
    for row in rows:
        rids.append(heap.insert(encode_record(row, metadata.schema)))

    heap.flush()
    return metadata, heap, rids


def test_histogram_empty():
    result = build_column_statistics([], 0)

    assert result.ndv == 0
    assert result.minimum is None
    assert result.maximum is None
    assert result.histogram == ()


def test_histogram_integer_values():
    result = build_column_statistics(
        range(1, 101),
        n_tuples=100,
        buckets=5,
    )

    assert result.ndv == 100
    assert result.minimum == 1
    assert result.maximum == 100
    assert len(result.histogram) == 5
    assert [bucket.count for bucket in result.histogram] == [20] * 5
    assert result.histogram[0].lower == 1
    assert result.histogram[-1].upper == 100


def test_histogram_duplicate_values():
    result = build_column_statistics(
        [1, 1, 1, 1, 2, 2, 2, 2],
        n_tuples=8,
        buckets=2,
    )

    assert result.ndv == 2
    assert len(result.histogram) == 2
    assert result.histogram[0].ndv == 1
    assert result.histogram[1].ndv == 1


def test_histogram_more_buckets_than_rows():
    result = build_column_statistics(
        [10, 20, 30],
        n_tuples=3,
        buckets=20,
    )

    assert len(result.histogram) == 3
    assert all(bucket.count == 1 for bucket in result.histogram)


def test_histogram_rejects_unsorted_input():
    with pytest.raises(ValueError, match="sorted"):
        build_column_statistics([3, 1, 2], 3)


def test_histogram_rejects_incorrect_count():
    with pytest.raises(ValueError, match="Expected"):
        build_column_statistics([1, 2], 3)


def test_analyze_table_statistics(tmp_path):
    rows = [
        (1, 20, "Alice"),
        (2, 30, "Bob"),
        (3, 30, "Carol"),
        (4, 40, "Dave"),
    ]
    metadata, _, _ = create_employee_table(tmp_path, rows)

    stats = analyze_table(
        tmp_path,
        "Emp",
        buckets=2,
        frames=8,
    )

    expected_width = sum(
        len(encode_record(row, metadata.schema)) for row in rows
    ) / len(rows)

    assert stats.table == "Emp"
    assert stats.n_tuples == 4
    assert stats.n_pages == 1
    assert stats.width == expected_width

    assert stats.columns["id"].ndv == 4
    assert stats.columns["age"].ndv == 3
    assert stats.columns["age"].minimum == 20
    assert stats.columns["age"].maximum == 40
    assert stats.columns["name"].ndv == 4

    assert sum(bucket.count for bucket in stats.columns["age"].histogram) == 4


def test_analyze_excludes_deleted_records(tmp_path):
    rows = [
        (1, 20, "Alice"),
        (2, 30, "Bob"),
        (3, 40, "Carol"),
    ]
    _, heap, rids = create_employee_table(tmp_path, rows)

    heap.delete(rids[1])
    heap.flush()

    stats = analyze_table(tmp_path, "Emp", buckets=2, frames=8)

    assert stats.n_tuples == 2
    assert stats.columns["age"].ndv == 2
    assert stats.columns["age"].minimum == 20
    assert stats.columns["age"].maximum == 40


def test_analyze_empty_table(tmp_path):
    create_employee_table(tmp_path, [])

    stats = analyze_table(tmp_path, "Emp", frames=8)

    assert stats.n_tuples == 0
    assert stats.n_pages == 0
    assert stats.width == 0
    assert all(column.ndv == 0 for column in stats.columns.values())


def test_analyze_is_deterministic(tmp_path):
    create_employee_table(
        tmp_path,
        [(i, i % 7, f"Employee{i}") for i in range(100)],
    )

    first = analyze_table(tmp_path, "Emp", frames=8)

    path = tmp_path / "optimizer_stats" / "Emp.json"
    first_bytes = path.read_bytes()

    second = analyze_table(tmp_path, "Emp", frames=8)
    second_bytes = path.read_bytes()

    assert first == second
    assert first_bytes == second_bytes


def test_analyze_persists_statistics(tmp_path):
    create_employee_table(
        tmp_path,
        [(1, 20, "Alice"), (2, 30, "Bob")],
    )

    stats = analyze_table(tmp_path, "Emp", frames=8)

    loaded = StatisticsStore(tmp_path).load("Emp")
    assert loaded == stats


def test_analyze_rejects_insufficient_frames(tmp_path):
    with pytest.raises(ValueError, match="4 frames"):
        analyze_table(tmp_path, "Emp", frames=3)


def test_analyze_rejects_invalid_buckets(tmp_path):
    with pytest.raises(ValueError, match="Bucket"):
        analyze_table(tmp_path, "Emp", buckets=0)


def test_analyze_cli(tmp_path, capsys):
    create_employee_table(
        tmp_path,
        [(1, 20, "Alice"), (2, 30, "Bob")],
    )

    result = main(
        [
            "analyze",
            "--db",
            str(tmp_path),
            "--table",
            "Emp",
            "--buckets",
            "2",
            "--frames",
            "8",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["table"] == "Emp"
    assert output["n_tuples"] == 2
    assert len(output["columns"]["age"]["histogram"]) == 2
