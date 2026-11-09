"""Regression tests for the integrated SQL benchmark runner."""

import csv

import pytest

from experiments.integration.run_benchmark import (
    main,
    root_q_error,
    run_workload,
    split_statements,
)
from src.integration.engine import DatabaseEngine


@pytest.fixture
def engine(tmp_path):
    database = DatabaseEngine(tmp_path / "database", frames=16)
    database.execute_sql("CREATE TABLE Numbers (id INT);")
    database.execute_sql("INSERT INTO Numbers VALUES (1);")
    database.execute_sql("INSERT INTO Numbers VALUES (2);")
    database.execute_sql("INSERT INTO Numbers VALUES (3);")
    database.analyze("Numbers")
    return database


def test_split_multiline_statements():
    statements = split_statements(
        """
        -- First query
        SELECT id
        FROM Numbers
        WHERE id > 1;

        /* Second query */
        SELECT * FROM Numbers;
        """
    )

    assert len(statements) == 2
    assert statements[0].startswith("SELECT id")
    assert statements[1] == "SELECT * FROM Numbers;"


def test_split_quoted_semicolon():
    statements = split_statements("SELECT 'a;b' FROM Numbers; SELECT id FROM Numbers;")

    assert len(statements) == 2
    assert "'a;b'" in statements[0]


def test_split_escaped_quote():
    statements = split_statements("SELECT 'it''s; fine' FROM Numbers;")

    assert len(statements) == 1
    assert "'it''s; fine'" in statements[0]


def test_split_rejects_incomplete_sql():
    with pytest.raises(ValueError, match="missing semicolon"):
        split_statements("SELECT * FROM Numbers")


def test_root_q_error():
    assert root_q_error(10, 10) == 1.0
    assert root_q_error(20, 10) == 2.0
    assert root_q_error(10, 20) == 2.0
    assert root_q_error(0, 0) == 1.0
    assert root_q_error(0, 5) == 5.0


def test_benchmark_collects_metrics(engine):
    records = run_workload(
        engine,
        [
            "SELECT * FROM Numbers;",
            "SELECT id FROM Numbers WHERE id > 1;",
        ],
    )

    assert len(records) == 2
    assert all(record["status"] == "ok" for record in records)

    assert records[0]["result_rows"] == 3
    assert records[0]["actual_root_rows"] == 3
    assert records[1]["result_rows"] == 2
    assert records[1]["actual_root_rows"] == 2

    for record in records:
        assert isinstance(record["page_reads"], int)
        assert isinstance(record["page_writes"], int)
        assert float(record["physical_execution_ms"]) >= 0
        assert float(record["end_to_end_ms"]) >= 0
        assert float(record["root_q_error"]) >= 1


def test_benchmark_records_query_errors(engine):
    records = run_workload(
        engine,
        [
            "SELECT * FROM MissingTable;",
            "SELECT * FROM Numbers;",
        ],
    )

    assert records[0]["status"] == "error"
    assert records[0]["error"]
    assert records[1]["status"] == "ok"


def test_benchmark_rejects_mutating_statements(engine):
    records = run_workload(
        engine,
        ["INSERT INTO Numbers VALUES (99);"],
    )

    assert records[0]["status"] == "error"

    remaining = engine.execute_sql("SELECT * FROM Numbers;")
    assert len(remaining[0].rows) == 3


def test_benchmark_cli_writes_csv(tmp_path):
    db = tmp_path / "database"
    setup = tmp_path / "setup.sql"
    workload = tmp_path / "workload.sql"
    output = tmp_path / "results" / "benchmark.csv"

    setup.write_text(
        """
        CREATE TABLE Numbers (id INT);
        INSERT INTO Numbers VALUES (1);
        INSERT INTO Numbers VALUES (2);
        """,
        encoding="utf-8",
    )
    workload.write_text(
        """
        SELECT * FROM Numbers;
        SELECT id FROM Numbers WHERE id > 1;
        """,
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--db",
            str(db),
            "--setup",
            str(setup),
            "--workload",
            str(workload),
            "--output",
            str(output),
            "--frames",
            "16",
        ]
    )

    assert exit_code == 0
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as file:
        records = list(csv.DictReader(file))

    assert len(records) == 2
    assert records[0]["status"] == "ok"
    assert records[0]["result_rows"] == "2"
    assert records[1]["result_rows"] == "1"


def test_benchmark_cli_reports_failures(tmp_path):
    db = tmp_path / "database"
    workload = tmp_path / "workload.sql"
    output = tmp_path / "results.csv"

    workload.write_text(
        "SELECT * FROM MissingTable;",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--db",
            str(db),
            "--workload",
            str(workload),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert output.exists()


def test_benchmark_cli_supports_analyze_setup(tmp_path):
    setup = tmp_path / "setup.sql"
    workload = tmp_path / "workload.sql"
    output = tmp_path / "results.csv"
    database = tmp_path / "database"

    setup.write_text(
        """
        CREATE TABLE Numbers (id INT);
        INSERT INTO Numbers VALUES (1);
        INSERT INTO Numbers VALUES (2);
        ANALYZE Numbers;
        """,
        encoding="utf-8",
    )

    workload.write_text(
        "SELECT * FROM Numbers;",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--db",
            str(database),
            "--setup",
            str(setup),
            "--workload",
            str(workload),
            "--output",
            str(output),
            "--frames",
            "16",
        ]
    )

    assert exit_code == 0
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["result_rows"] == "2"
