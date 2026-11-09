"""End-to-end regression tests for the 25-query SQL workload."""

from pathlib import Path

import pytest

from experiments.integration.run_benchmark import (
    run_workload,
    split_statements,
)
from src.integration.engine import DatabaseEngine

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments" / "integration"

EXPECTED_ROWS = [
    10,
    5,
    8,
    10,
    10,
    3,
    5,
    3,
    4,
    2,
    2,
    2,
    3,
    3,
    5,
    4,
    0,
    10,
    3,
    5,
    10,
    5,
    8,
    5,
    17,
]


@pytest.fixture(scope="module")
def workload_results(tmp_path_factory):
    """Build a fresh database and execute the complete workload."""
    database = tmp_path_factory.mktemp("workload25")
    engine = DatabaseEngine(database, frames=16)

    setup = (EXPERIMENTS / "workload25_setup.sql").read_text(encoding="utf-8")
    workload = (EXPERIMENTS / "workload25.sql").read_text(encoding="utf-8")

    for statement in split_statements(setup):
        command = statement.strip().rstrip(";").strip()

        if command.upper().startswith("ANALYZE "):
            parts = command.split()

            if len(parts) != 2:
                raise ValueError(f"Invalid ANALYZE command: {command}")

            engine.analyze(parts[1])
        else:
            engine.execute_sql(statement)

    return run_workload(engine, split_statements(workload))


def test_workload_has_25_queries(workload_results):
    assert len(workload_results) == 25


@pytest.mark.parametrize(
    ("index", "expected"),
    list(enumerate(EXPECTED_ROWS)),
)
def test_workload_query(workload_results, index, expected):
    result = workload_results[index]

    assert result["status"] == "ok", f"{result['query_id']}: {result['error']}"
    assert result["result_rows"] == expected, (
        f"{result['query_id']}: expected {expected} rows, got {result['result_rows']}"
    )


def test_workload_metrics(workload_results):
    for result in workload_results:
        assert result["status"] == "ok"
        assert result["end_to_end_ms"] != ""
        assert float(result["end_to_end_ms"]) >= 0
        assert int(result["page_reads"]) >= 0
        assert int(result["page_writes"]) >= 0
        assert int(result["total_page_io"]) >= 0
        assert int(result["actual_root_rows"]) == result["result_rows"]
