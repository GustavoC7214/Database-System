"""Tests for the optimizer logical-plan CLI."""

import json

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

    return tmp_path


def save_stats(database, table, rows=100, pages=5):
    StatisticsStore(database).save(
        TableStatistics(
            table=table,
            n_tuples=rows,
            n_pages=pages,
            width=16.0,
        )
    )


def run_plan(database, capsys, sql, *options):
    result = main(
        [
            "plan",
            "--db",
            str(database),
            "--sql",
            sql,
            *options,
        ]
    )

    assert result == 0
    return json.loads(capsys.readouterr().out)


def test_simple_scan_without_statistics(database, capsys):
    plans = run_plan(
        database,
        capsys,
        "SELECT * FROM Emp;",
    )

    assert len(plans) == 1
    assert plans[0]["op"] == "project"


def test_projection_without_statistics(database, capsys):
    plans = run_plan(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    assert plans[0]["columns"] == ["Emp.name"]


def test_join_without_statistics_uses_fallback(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_plan(database, capsys, sql)

    assert len(plans) == 1
    assert plans[0]["op"] == "project"

    # Fallback planning must not create fake ANALYZE files.
    store = StatisticsStore(database)
    assert store.load("Emp") is None
    assert store.load("Dept") is None


def test_join_without_statistics_allowed_when_disabled(
    database,
    capsys,
):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_plan(
        database,
        capsys,
        sql,
        "--no-join-order",
    )

    assert len(plans) == 1
    assert plans[0]["op"] == "project"


def test_join_with_persisted_statistics(database, capsys):
    save_stats(database, "Emp")
    save_stats(database, "Dept")

    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_plan(database, capsys, sql)

    assert len(plans) == 1
    assert plans[0]["op"] == "project"


def test_unrelated_table_statistics_not_required(
    database,
    capsys,
):
    save_stats(database, "Emp")
    save_stats(database, "Dept")

    plans = run_plan(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    assert len(plans) == 1


def test_deterministic_json_output(database, capsys):
    save_stats(database, "Emp")
    save_stats(database, "Dept")

    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    run_plan(database, capsys, sql)
    first = capsys.readouterr().out

    run_plan(database, capsys, sql)
    second = capsys.readouterr().out

    assert first == second


def test_invalid_buffer_count(database, capsys):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--sql",
                "SELECT * FROM Emp;",
                "--frames",
                "2",
            ]
        )

    assert exc.value.code == 2
    assert "--frames must be at least 3" in capsys.readouterr().err


def test_invalid_sql_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--sql",
                "SELECT FROM;",
            ]
        )

    assert exc.value.code == 2
    assert capsys.readouterr().err


def test_missing_database_rejected(tmp_path, capsys):
    missing = tmp_path / "missing"

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(missing),
                "--sql",
                "SELECT * FROM Emp;",
            ]
        )

    assert exc.value.code == 2
    assert "Database directory does not exist" in (capsys.readouterr().err)


def test_empty_sql_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plan",
                "--db",
                str(database),
                "--sql",
                "",
            ]
        )

    assert exc.value.code == 2
    assert capsys.readouterr().err


def test_rewrites_option_accepted(database, capsys):
    plans = run_plan(
        database,
        capsys,
        "SELECT name FROM Emp;",
        "--rewrites",
        "--no-join-order",
    )

    assert len(plans) == 1
