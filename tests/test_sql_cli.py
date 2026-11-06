"""Tests for the Module 3 SQL command-line interface."""

import json
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from src.sql.catalog import SchemaCatalog
from src.sql.cli import main
from src.storage.catalog import Catalog, TableMetadata


class FakeCatalog:
    def __init__(self) -> None:
        self.tables = {
            "Emp": TableMetadata(
                name="Emp",
                filename="Emp.db",
                schema=[
                    ("eid", "INT"),
                    ("name", "VARCHAR(40)"),
                    ("age", "INT"),
                    ("did", "INT"),
                    ("salary", "INT"),
                ],
            ),
            "Dept": TableMetadata(
                name="Dept",
                filename="Dept.db",
                schema=[
                    ("did", "INT"),
                    ("title", "VARCHAR(60)"),
                ],
            ),
        }

    def get_table(self, name: str) -> TableMetadata:
        if name not in self.tables:
            raise ValueError(f"Unknown table: {name}")
        return self.tables[name]

    def list_tables(self) -> list[str]:
        return list(self.tables)


@pytest.fixture
def fake_catalog():
    return SchemaCatalog(cast(Catalog, FakeCatalog()))


@pytest.fixture
def catalog_loader(fake_catalog, tmp_path, monkeypatch):
    """Use a real temporary directory with a mocked catalog loader."""
    db_dir = tmp_path / "fake-db"
    db_dir.mkdir()
    (db_dir / "catalog.db").touch()

    monkeypatch.chdir(tmp_path)

    with patch(
        "src.sql.cli.SchemaCatalog.from_directory",
        return_value=fake_catalog,
    ) as loader:
        yield loader


def test_parse_query_success(capsys):
    result = main(
        [
            "parse",
            "--query",
            "SELECT name FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "OK: 1 SQL statements parsed.\n"
    assert captured.err == ""


def test_parse_explain_indented_tree(capsys):
    result = main(
        [
            "parse",
            "--query",
            "SELECT name FROM Emp;",
            "--explain",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert "Statement 1:" in captured.out
    assert "  Select" in captured.out
    assert "    source:" in captured.out
    assert "      Table" in captured.out
    assert "        name: Emp" in captured.out
    assert "Column" in captured.out
    assert "name: name" in captured.out


def test_parse_multiple_statements(capsys):
    result = main(
        [
            "parse",
            "--query",
            "SELECT name FROM Emp; SELECT title FROM Dept;",
        ]
    )

    assert result == 0
    assert "2 SQL statements parsed" in capsys.readouterr().out


def test_parse_syntax_error(capsys):
    result = main(
        [
            "parse",
            "--query",
            "SELECT FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: syntax:" in captured.err
    assert captured.out == ""


def test_parse_from_file(tmp_path, capsys):
    source = tmp_path / "query.sql"
    source.write_text(
        "SELECT name FROM Emp;",
        encoding="utf-8",
    )

    result = main(
        [
            "parse",
            "--file",
            str(source),
        ]
    )

    assert result == 0
    assert "1 SQL statements parsed" in capsys.readouterr().out


def test_missing_sql_file(capsys, tmp_path):
    result = main(
        [
            "parse",
            "--file",
            str(tmp_path / "missing.sql"),
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: schema:" in captured.err
    assert "at line 1, column 1" in captured.err


def test_check_valid_query(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Emp WHERE age > 20;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert "1 SQL statements validated" in captured.out
    assert captured.err == ""
    catalog_loader.assert_called_once_with("fake-db")


def test_check_unknown_table(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Missing;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "unknown table" in captured.err
    assert captured.out == ""


def test_check_unknown_column(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT missing FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "unknown column" in captured.err


def test_check_type_error(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Emp WHERE age = 'twenty';",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: type:" in captured.err


def test_check_ambiguous_column(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT did FROM Emp, Dept;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: ambiguity:" in captured.err


def test_check_aggregate_error(catalog_loader, capsys):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            "SELECT SUM(name) FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: aggregate:" in captured.err


def test_compile_json(catalog_loader, capsys):
    result = main(
        [
            "compile",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Emp WHERE age > 20;",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    plans = json.loads(captured.out)

    assert result == 0
    assert captured.err == ""
    assert len(plans) == 1
    assert plans[0]["op"] == "project"
    assert plans[0]["columns"] == ["Emp.name"]
    assert plans[0]["child"]["op"] == "select"


def test_compile_multiple_queries(catalog_loader, capsys):
    result = main(
        [
            "compile",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Emp; SELECT title FROM Dept;",
            "--json",
        ]
    )

    plans = json.loads(capsys.readouterr().out)

    assert result == 0
    assert len(plans) == 2


def test_compile_human_readable(catalog_loader, capsys):
    result = main(
        [
            "compile",
            "--db",
            "fake-db",
            "--query",
            "SELECT name FROM Emp;",
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Logical plan 1:" in output
    assert '"op": "project"' in output


def test_compile_invalid_query_no_json(catalog_loader, capsys):
    result = main(
        [
            "compile",
            "--db",
            "fake-db",
            "--query",
            "SELECT missing FROM Emp;",
            "--json",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "unknown column" in captured.err


@pytest.mark.parametrize(
    "command",
    ["check", "compile"],
)
def test_unsupported_create_table(catalog_loader, capsys, command):
    result = main(
        [
            command,
            "--db",
            "fake-db",
            "--query",
            "CREATE TABLE NewTable (id INT);",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "SELECT queries only" in captured.err


def test_real_module_entry_point():
    root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.sql.cli",
            "parse",
            "--query",
            "SELECT name FROM Emp;",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "1 SQL statements parsed" in result.stdout
    assert result.stderr == ""


def test_check_missing_database_directory(tmp_path, capsys):
    missing_db = tmp_path / "missing"

    result = main(
        [
            "check",
            "--db",
            str(missing_db),
            "--query",
            "SELECT * FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: schema:" in captured.err
    assert "at line 1, column 1" in captured.err
    assert captured.out == ""
    assert "Database directory does not exist" in captured.err


def test_compile_missing_catalog_file(tmp_path, capsys):
    db_dir = tmp_path / "empty_db"
    db_dir.mkdir()

    result = main(
        [
            "compile",
            "--db",
            str(db_dir),
            "--query",
            "SELECT * FROM Emp;",
            "--json",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "error: schema:" in captured.err
    assert "at line 1, column 1" in captured.err
    assert captured.out == ""
    assert "Database catalog does not exist" in captured.err


@pytest.mark.parametrize(
    "query, category",
    [
        ("SELECT FROM Emp;", "syntax"),
        ("SELECT missing FROM Emp;", "name"),
        ("SELECT did FROM Emp, Dept;", "ambiguity"),
        ("SELECT age FROM Emp WHERE age = '30';", "type"),
        ("SELECT SUM(name) FROM Emp;", "aggregate"),
    ],
)
def test_cli_error_format(
    catalog_loader,
    capsys,
    query,
    category,
):
    result = main(
        [
            "check",
            "--db",
            "fake-db",
            "--query",
            query,
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err.startswith(f"error: {category}:")
    assert " at line " in captured.err
    assert ", column " in captured.err


def test_cli_missing_catalog_error_format(tmp_path, capsys):
    db_dir = tmp_path / "empty"
    db_dir.mkdir()

    result = main(
        [
            "check",
            "--db",
            str(db_dir),
            "--query",
            "SELECT * FROM Emp;",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err.startswith("error: schema:")
    assert "at line 1, column 1" in captured.err
