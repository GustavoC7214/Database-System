"""Tests for optimizer CLI physical-plan export."""

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


def run_physical(database, capsys, sql, *options):
    result = main(
        [
            "plan",
            "--db",
            str(database),
            "--sql",
            sql,
            "--physical",
            *options,
        ]
    )

    assert result == 0
    return json.loads(capsys.readouterr().out)


def test_scan_physical_export(database, capsys):
    plans = run_physical(
        database,
        capsys,
        "SELECT * FROM Emp;",
    )

    assert len(plans) == 1
    assert plans[0]["op"] in {"seqscan", "project"}


def test_projection_physical_export(database, capsys):
    plans = run_physical(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    assert plans[0]["op"] == "project"
    assert plans[0]["columns"] == ["Emp.name"]
    assert plans[0]["child"]["op"] == "seqscan"


def test_filter_physical_export(database, capsys):
    plans = run_physical(
        database,
        capsys,
        "SELECT name FROM Emp WHERE eid > 10;",
    )

    assert plans[0]["op"] == "project"

    filter_node = plans[0]["child"]

    assert filter_node["op"] == "filter"
    assert filter_node["column"] == "Emp.eid"
    assert filter_node["comparison"] == ">"
    assert filter_node["value"] == 10


def test_join_physical_export(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_physical(
        database,
        capsys,
        sql,
        "--no-join-order",
    )

    join_node = plans[0]["child"]

    assert join_node["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    assert join_node["left_key"] == "Emp.did"
    assert join_node["right_key"] == "Dept.did"


def test_join_ordering_physical_export(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_physical(database, capsys, sql)

    assert len(plans) == 1
    assert plans[0]["op"] == "project"


def test_physical_json_deterministic(database, capsys):
    sql = "SELECT name FROM Emp;"

    first = run_physical(database, capsys, sql)
    second = run_physical(database, capsys, sql)

    assert first == second


def test_multiple_physical_plans(database, capsys):
    plans = run_physical(
        database,
        capsys,
        "SELECT name FROM Emp; SELECT title FROM Dept;",
    )

    assert len(plans) == 2


def test_physical_scan_without_statistics(database, capsys):
    StatisticsStore(database).delete("Emp")

    plans = run_physical(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    assert plans[0]["child"]["op"] == "seqscan"


def test_physical_join_uses_fallback(database, capsys):
    StatisticsStore(database).delete("Emp")

    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = run_physical(
        database,
        capsys,
        sql,
        "--no-join-order",
    )

    join = plans[0]["child"]

    assert join["op"] in {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    assert StatisticsStore(database).load("Emp") is None


def test_compound_filter_rejected(database, capsys):
    sql = """
    SELECT name FROM Emp
    WHERE eid > 10 OR did = 2;
    """

    with pytest.raises(SystemExit) as exc:
        run_physical(database, capsys, sql)

    assert exc.value.code == 2
    assert "Only AND compound filters are supported" in capsys.readouterr().err


def test_alias_rejected(database, capsys):
    sql = "SELECT e.name FROM Emp AS e;"

    with pytest.raises(SystemExit) as exc:
        run_physical(database, capsys, sql)

    assert exc.value.code == 2
    assert capsys.readouterr().err


def test_physical_requires_four_frames(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_physical(
            database,
            capsys,
            "SELECT name FROM Emp;",
            "--frames",
            "3",
        )

    assert exc.value.code == 2
    assert "--physical requires at least 4" in (capsys.readouterr().err)


def test_invalid_sql_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_physical(
            database,
            capsys,
            "SELECT FROM;",
        )

    assert exc.value.code == 2
    assert capsys.readouterr().err
