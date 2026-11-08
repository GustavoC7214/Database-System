"""Tests for the optimizer EXPLAIN CLI."""

import pytest

from src.optimizer.cli import main
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.storage.catalog import Catalog


@pytest.fixture
def database(tmp_path):
    catalog = Catalog(tmp_path)

    catalog.create_table(
        "Emp",
        "eid:INT,did:INT,name:VARCHAR(30)",
    )
    catalog.create_table(
        "Dept",
        "did:INT,title:VARCHAR(30)",
    )

    store = StatisticsStore(tmp_path)

    for name, rows, pages in (
        ("Emp", 1000, 20),
        ("Dept", 100, 5),
    ):
        store.save(
            TableStatistics(
                table=name,
                n_tuples=rows,
                n_pages=pages,
                width=32.0,
            )
        )

    return tmp_path


def explain(database, capsys, sql, *options):
    result = main(
        [
            "explain",
            "--db",
            str(database),
            "--sql",
            sql,
            *options,
        ]
    )

    assert result == 0
    return capsys.readouterr().out


def test_scan_explain(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT * FROM Emp;",
    )

    assert "OPTIMIZER EXPLAIN" in output
    assert "SCAN [seqscan]" in output
    assert "Estimated output rows: 1000" in output
    assert "Estimated total I/O:" in output


def test_projection_explain(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    assert "PROJECT [project]" in output
    assert "SCAN [seqscan]" in output


def test_filter_explain(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT name FROM Emp WHERE eid > 10;",
    )

    assert "SELECT [filter]" in output
    assert "local_io=0" in output


def test_join_explain(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    output = explain(
        database,
        capsys,
        sql,
        "--no-join-order",
    )

    assert "JOIN [" in output
    assert "Estimated total I/O:" in output
    assert "rows=" in output
    assert "pages=" in output


def test_explain_is_deterministic(database, capsys):
    sql = "SELECT name FROM Emp;"

    first = explain(database, capsys, sql)
    second = explain(database, capsys, sql)

    assert first == second


def test_multiple_queries(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT name FROM Emp; SELECT title FROM Dept;",
    )

    assert "Query 1" in output
    assert "Query 2" in output


def test_missing_statistics_uses_fallback(database, capsys):
    StatisticsStore(database).delete("Emp")

    result = main(
        [
            "explain",
            "--db",
            str(database),
            "--sql",
            "SELECT * FROM Emp;",
        ]
    )

    assert result == 0

    output = capsys.readouterr().out

    assert "Estimated output rows: 1000" in output
    assert "Estimated total I/O: 20" in output
    assert "SCAN [seqscan] rows=1000 pages=20" in output

    # Fallback estimates must not be persisted as ANALYZE results.
    assert StatisticsStore(database).load("Emp") is None


def test_invalid_frames_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "explain",
                "--db",
                str(database),
                "--sql",
                "SELECT * FROM Emp;",
                "--frames",
                "2",
            ]
        )

    assert exc.value.code == 2
    assert "--frames must be at least 3" in (capsys.readouterr().err)


def test_explain_does_not_claim_measured_io(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT * FROM Emp;",
    )

    assert "not measured disk I/O" in output
    assert "not guaranteed physical lowering" in output


def test_rewrites_option_accepted(database, capsys):
    output = explain(
        database,
        capsys,
        "SELECT name FROM Emp;",
        "--rewrites",
        "--no-join-order",
    )

    assert "OPTIMIZER EXPLAIN" in output
