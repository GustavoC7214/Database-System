"""Tests for the Module 2 execution CLI."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.execution.cli import main


@pytest.fixture
def plan_file(tmp_path):
    """Create a minimal physical-plan JSON file."""
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps({"op": "seqscan", "table": "Employees"}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def execution_result():
    """Create representative execution results."""
    return SimpleNamespace(
        schema=[
            ("Employees.id", "INT"),
            ("Employees.name", "VARCHAR"),
        ],
        rows=[
            (1, "Alice"),
            (2, "Bob"),
        ],
        counters={
            "tuples_out": 2,
            "comparisons": 0,
            "page_reads": 1,
            "page_writes": 0,
        },
        operator_stats=[
            {
                "operator": "SeqScan",
                "depth": 0,
                "counters": {
                    "tuples_out": 2,
                    "comparisons": 0,
                    "page_reads": 1,
                    "page_writes": 0,
                },
            }
        ],
    )


def test_run_json_output(tmp_path, plan_file, execution_result, capsys):
    """Run should produce machine-readable JSON."""
    with patch("src.execution.cli.PhysicalPlanExecutor") as executor_class:
        executor_class.return_value.execute_file.return_value = execution_result

        status = main(
            [
                "run",
                "--db",
                str(tmp_path),
                "--plan",
                str(plan_file),
                "--frames",
                "4",
                "--json",
            ]
        )

    assert status == 0

    output = json.loads(capsys.readouterr().out)

    assert output["schema"] == [
        {"name": "Employees.id", "type": "INT"},
        {"name": "Employees.name", "type": "VARCHAR"},
    ]
    assert output["rows"] == [[1, "Alice"], [2, "Bob"]]
    assert output["totals"]["tuples_out"] == 2
    assert output["totals"]["page_reads"] == 1


def test_trace_indentation(tmp_path, plan_file, execution_result, capsys):
    """Trace should indent child operators."""
    execution_result.operator_stats.append(
        {
            "operator": "SeqScan",
            "depth": 1,
            "counters": {
                "tuples_out": 2,
                "comparisons": 0,
                "page_reads": 1,
                "page_writes": 0,
            },
        }
    )

    with patch("src.execution.cli.PhysicalPlanExecutor") as executor_class:
        executor_class.return_value.execute_file.return_value = execution_result

        status = main(
            [
                "trace",
                "--db",
                str(tmp_path),
                "--plan",
                str(plan_file),
                "--frames",
                "4",
            ]
        )

    assert status == 0

    output = capsys.readouterr().out
    assert "SeqScan" in output
    assert "  SeqScan" in output
    assert "Execution totals:" in output


@pytest.mark.parametrize("frames", ["0", "1", "3", "-1"])
def test_invalid_frame_budget(tmp_path, plan_file, frames):
    """Execution should reject budgets below four frames."""
    with pytest.raises(SystemExit) as error:
        main(
            [
                "run",
                "--db",
                str(tmp_path),
                "--plan",
                str(plan_file),
                "--frames",
                frames,
            ]
        )

    assert error.value.code == 2


def test_missing_plan_file(tmp_path, capsys):
    """Missing plan files should produce a CLI error."""
    with pytest.raises(SystemExit) as error:
        main(
            [
                "run",
                "--db",
                str(tmp_path),
                "--plan",
                str(tmp_path / "missing.json"),
            ]
        )

    assert error.value.code == 2
    assert "Plan file does not exist" in capsys.readouterr().err


def test_malformed_json(tmp_path, capsys):
    """Malformed JSON should fail without a traceback."""
    plan = tmp_path / "invalid.json"
    plan.write_text("{invalid json", encoding="utf-8")

    status = main(
        [
            "run",
            "--db",
            str(tmp_path),
            "--plan",
            str(plan),
            "--frames",
            "4",
        ]
    )

    assert status == 1
    assert "Execution error:" in capsys.readouterr().err


def test_unknown_operator(tmp_path, capsys):
    """Unknown operators should be rejected."""
    plan = tmp_path / "unknown.json"
    plan.write_text(
        json.dumps({"op": "nonexistent_operator"}),
        encoding="utf-8",
    )

    status = main(
        [
            "run",
            "--db",
            str(tmp_path),
            "--plan",
            str(plan),
            "--frames",
            "4",
        ]
    )

    assert status == 1
    assert "Execution error:" in capsys.readouterr().err
