"""End-to-end tests for the Module 2 execution CLI."""

import json

import pytest

from src.execution.cli import main
from src.execution.plan_executor import PhysicalPlanExecutor
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


@pytest.fixture
def database_dir(tmp_path):
    """Create a real disk-backed database with two tables."""
    catalog = Catalog(tmp_path)

    tables = {
        "Employees": (
            "id:INT,department:INT,name:VARCHAR(30),salary:INT",
            [
                (1, 10, "Alice", 70000),
                (2, 20, "Bob", 45000),
                (3, 10, "Charlie", 80000),
                (4, 30, "David", 55000),
                (5, 20, "Eve", 60000),
            ],
        ),
        "Departments": (
            "id:INT,label:VARCHAR(30)",
            [
                (10, "Engineering"),
                (20, "Sales"),
                (30, "Operations"),
            ],
        ),
    }

    for name, (schema, rows) in tables.items():
        metadata = catalog.create_table(name, schema)
        heap = HeapFile(tmp_path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()

    return tmp_path


def write_plan(tmp_path, plan):
    """Write a physical plan to a JSON file."""
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def run_cli(command, database_dir, plan, *extra):
    """Invoke the CLI with a four-frame memory budget."""
    return main(
        [
            command,
            "--db",
            str(database_dir),
            "--plan",
            str(plan),
            "--frames",
            "4",
            *extra,
        ]
    )


def test_real_scan_json(database_dir, tmp_path, capsys):
    """Run a disk-backed sequential scan through the CLI."""
    plan = write_plan(
        tmp_path,
        {"op": "seqscan", "table": "Employees"},
    )

    assert run_cli("run", database_dir, plan, "--json") == 0

    output = json.loads(capsys.readouterr().out)

    assert output["schema"][0] == {
        "name": "Employees.id",
        "type": "INT",
    }
    assert output["rows"] == [
        [1, 10, "Alice", 70000],
        [2, 20, "Bob", 45000],
        [3, 10, "Charlie", 80000],
        [4, 30, "David", 55000],
        [5, 20, "Eve", 60000],
    ]
    assert output["totals"]["tuples_out"] == 5
    assert output["totals"]["page_reads"] >= 1


def test_real_filter_project_limit(database_dir, tmp_path, capsys):
    """Execute a multi-operator pipeline through the CLI."""
    plan = write_plan(
        tmp_path,
        {
            "op": "limit",
            "count": 2,
            "child": {
                "op": "project",
                "columns": ["Employees.name"],
                "child": {
                    "op": "filter",
                    "column": "Employees.salary",
                    "comparison": ">",
                    "value": 50000,
                    "child": {
                        "op": "seqscan",
                        "table": "Employees",
                    },
                },
            },
        },
    )

    assert run_cli("run", database_dir, plan, "--json") == 0

    output = json.loads(capsys.readouterr().out)

    assert output["rows"] == [["Alice"], ["Charlie"]]
    assert output["totals"]["tuples_out"] == 2
    assert output["totals"]["comparisons"] >= 2
    assert output["totals"]["page_reads"] >= 1


def test_real_join_json(database_dir, tmp_path, capsys):
    """Execute a disk-backed join with duplicate matching keys."""
    plan = write_plan(
        tmp_path,
        {
            "op": "nested_loop_join",
            "left_key": "Employees.department",
            "right_key": "Departments.id",
            "left": {"op": "seqscan", "table": "Employees"},
            "right": {"op": "seqscan", "table": "Departments"},
        },
    )

    assert run_cli("run", database_dir, plan, "--json") == 0

    output = json.loads(capsys.readouterr().out)

    assert len(output["rows"]) == 5
    assert output["totals"]["tuples_out"] == 5
    assert output["totals"]["comparisons"] >= 15


def test_real_trace_indentation(database_dir, tmp_path, capsys):
    """Trace should show the operator tree and its counters."""
    plan = write_plan(
        tmp_path,
        {
            "op": "filter",
            "column": "Employees.salary",
            "comparison": ">",
            "value": 50000,
            "child": {"op": "seqscan", "table": "Employees"},
        },
    )

    assert run_cli("trace", database_dir, plan) == 0

    output = capsys.readouterr().out

    assert "Filter" in output
    assert "  SeqScan" in output
    assert "tuples_out=" in output
    assert "page_reads=" in output
    assert "Execution totals:" in output


def test_unknown_table(database_dir, tmp_path, capsys):
    """Unknown tables must fail with a nonzero exit status."""
    plan = write_plan(
        tmp_path,
        {"op": "seqscan", "table": "DoesNotExist"},
    )

    assert run_cli("run", database_dir, plan, "--json") == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Execution error:" in captured.err


def test_unknown_column(database_dir, tmp_path, capsys):
    """Unknown columns must fail with a nonzero exit status."""
    plan = write_plan(
        tmp_path,
        {
            "op": "project",
            "columns": ["Employees.nonexistent"],
            "child": {"op": "seqscan", "table": "Employees"},
        },
    )

    assert run_cli("run", database_dir, plan, "--json") == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Execution error:" in captured.err


def test_executor_releases_frames(database_dir):
    """Execution must release all frame reservations and pins."""
    executor = PhysicalPlanExecutor(database_dir, frames=4)

    result = executor.execute(
        {
            "op": "sort",
            "keys": [["Employees.salary", "DESC"]],
            "child": {"op": "seqscan", "table": "Employees"},
        }
    )

    assert len(result.rows) == 5
    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)
