"""Tests for the Module 4 logical JSON CLI contract."""

import json

import pytest

from src.optimizer.cli import main
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.storage.catalog import Catalog


@pytest.fixture
def database(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Emp", "eid:INT,did:INT")
    catalog.create_table("Dept", "did:INT")

    store = StatisticsStore(tmp_path)

    store.save(
        TableStatistics(
            table="Emp",
            n_tuples=1000,
            n_pages=20,
            width=8.0,
        )
    )
    store.save(
        TableStatistics(
            table="Dept",
            n_tuples=100,
            n_pages=5,
            width=4.0,
        )
    )

    return tmp_path


def write_plan(tmp_path, plan):
    path = tmp_path / "logical.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def test_logical_scan_produces_physical_object(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {"op": "scan", "table": "Emp"},
    )

    assert (
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(path),
                "--json",
            ]
        )
        == 0
    )

    physical = json.loads(capsys.readouterr().out)

    assert physical == {"op": "seqscan", "table": "Emp"}


def test_logical_projection(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {
            "op": "project",
            "columns": ["Emp.eid"],
            "child": {"op": "scan", "table": "Emp"},
        },
    )

    assert (
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )
        == 0
    )

    physical = json.loads(capsys.readouterr().out)

    assert physical["op"] == "project"
    assert physical["columns"] == ["Emp.eid"]
    assert physical["child"]["op"] == "seqscan"


def test_logical_join(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {
            "op": "join",
            "condition": "Emp.did = Dept.did",
            "left": {"op": "scan", "table": "Emp"},
            "right": {"op": "scan", "table": "Dept"},
        },
    )

    assert (
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )
        == 0
    )

    physical = json.loads(capsys.readouterr().out)

    assert physical["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }


def test_logical_explain(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {"op": "scan", "table": "Emp"},
    )

    assert (
        main(
            [
                "explain",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out

    assert "Estimated output rows: 1000" in output
    assert "Estimated total I/O:" in output


def test_logical_dp_table(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {
            "op": "join",
            "condition": "Emp.did = Dept.did",
            "left": {"op": "scan", "table": "Emp"},
            "right": {"op": "scan", "table": "Dept"},
        },
    )

    assert (
        main(
            [
                "dp-table",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out

    assert "Emp" in output
    assert "Dept" in output


def test_invalid_json_rejected(database, tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )

    assert exc.value.code == 2
    assert "Invalid logical-plan JSON" in capsys.readouterr().err


def test_missing_file_rejected(database, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(tmp_path / "missing.json"),
            ]
        )

    assert exc.value.code == 2
    assert "Cannot read logical plan" in capsys.readouterr().err


def test_sql_and_logical_are_mutually_exclusive(database, tmp_path):
    path = write_plan(
        tmp_path,
        {"op": "scan", "table": "Emp"},
    )

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--sql",
                "SELECT * FROM Emp;",
                "--logical",
                str(path),
            ]
        )

    assert exc.value.code == 2


def test_logical_input_is_not_modified(database, tmp_path, capsys):
    original = {
        "op": "project",
        "columns": ["Emp.eid"],
        "child": {"op": "scan", "table": "Emp"},
    }

    path = write_plan(tmp_path, original)

    assert (
        main(
            [
                "plan",
                "--db",
                str(database),
                "--logical",
                str(path),
            ]
        )
        == 0
    )

    capsys.readouterr()

    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_logical_physical_output_is_deterministic(database, tmp_path, capsys):
    path = write_plan(
        tmp_path,
        {"op": "scan", "table": "Emp"},
    )

    arguments = [
        "plan",
        "--db",
        str(database),
        "--logical",
        str(path),
    ]

    assert main(arguments) == 0
    first = capsys.readouterr().out

    assert main(arguments) == 0
    second = capsys.readouterr().out

    assert first == second


def test_logical_dp_table_without_statistics(database, tmp_path, capsys):
    store = StatisticsStore(database)
    store.delete("Emp")
    store.delete("Dept")

    logical = {
        "op": "join",
        "condition": "Emp.did = Dept.did",
        "left": {"op": "scan", "table": "Emp"},
        "right": {"op": "scan", "table": "Dept"},
    }

    path = tmp_path / "logical_dp_no_stats.json"
    path.write_text(json.dumps(logical), encoding="utf-8")

    result = main(
        [
            "dp-table",
            "--db",
            str(database),
            "--logical",
            str(path),
        ]
    )

    assert result == 0

    output = capsys.readouterr().out

    assert "Emp" in output
    assert "Dept" in output
    assert store.load("Emp") is None
    assert store.load("Dept") is None
