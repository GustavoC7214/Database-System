"""Tests for the optimizer DP join-order CLI."""

import pytest

from src.optimizer.cli import main
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.storage.catalog import Catalog


@pytest.fixture
def database(tmp_path):
    catalog = Catalog(tmp_path)

    catalog.create_table("A", "id:INT,bid:INT")
    catalog.create_table("B", "id:INT,cid:INT")
    catalog.create_table("C", "id:INT,value:INT")

    store = StatisticsStore(tmp_path)

    for name, rows, pages in (
        ("A", 1000, 20),
        ("B", 100, 5),
        ("C", 500, 10),
    ):
        store.save(
            TableStatistics(
                table=name,
                n_tuples=rows,
                n_pages=pages,
                width=16.0,
            )
        )

    return tmp_path


def run_dp(database, capsys, *arguments):
    result = main(
        [
            "dp-table",
            "--db",
            str(database),
            *arguments,
        ]
    )

    assert result == 0
    return capsys.readouterr().out


def test_two_table_dp(database, capsys):
    output = run_dp(
        database,
        capsys,
        "--tables",
        "A",
        "B",
        "--join",
        "A.bid=B.id",
    )

    assert output
    assert "A" in output
    assert "B" in output


def test_three_table_dp(database, capsys):
    output = run_dp(
        database,
        capsys,
        "--tables",
        "A",
        "B",
        "C",
        "--join",
        "A.bid=B.id",
        "--join",
        "B.cid=C.id",
    )

    assert output
    assert "A" in output
    assert "B" in output
    assert "C" in output


def test_dp_output_deterministic(database, capsys):
    arguments = (
        "--tables",
        "A",
        "B",
        "--join",
        "A.bid=B.id",
    )

    first = run_dp(database, capsys, *arguments)
    second = run_dp(database, capsys, *arguments)

    assert first == second


def test_missing_statistics_uses_fallback(database, capsys):
    store = StatisticsStore(database)
    store.delete("A")

    output = run_dp(
        database,
        capsys,
        "--tables",
        "A",
        "B",
        "--join",
        "A.bid=B.id",
    )

    assert output
    assert "A" in output
    assert "B" in output

    # The fallback must not create persisted ANALYZE statistics.
    assert store.load("A") is None


def test_unknown_join_column(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "B",
            "--join",
            "A.missing=B.id",
        )

    assert exc.value.code == 2
    assert "Unknown join column" in capsys.readouterr().err


def test_join_references_unlisted_table(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "B",
            "--join",
            "A.bid=C.id",
        )

    assert exc.value.code == 2
    assert "not in --tables" in capsys.readouterr().err


def test_invalid_join_syntax(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "B",
            "--join",
            "A.bid>B.id",
        )

    assert exc.value.code == 2
    assert "Invalid join condition" in capsys.readouterr().err


def test_duplicate_tables_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "A",
            "--join",
            "A.bid=B.id",
        )

    assert exc.value.code == 2
    assert "Duplicate tables" in capsys.readouterr().err


def test_single_table_rejected(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "--join",
            "A.id=B.id",
        )

    assert exc.value.code == 2
    assert "at least two tables" in capsys.readouterr().err


def test_invalid_frames(database, capsys):
    with pytest.raises(SystemExit) as exc:
        run_dp(
            database,
            capsys,
            "--tables",
            "A",
            "B",
            "--join",
            "A.bid=B.id",
            "--frames",
            "2",
        )

    assert exc.value.code == 2
    assert "--frames must be at least 3" in (capsys.readouterr().err)
