"""Integration tests for the unified database engine."""

import pytest

from src.integration.engine import DatabaseEngine
from src.integration.shell import run_command, split_complete_statements


@pytest.fixture
def engine(tmp_path):
    return DatabaseEngine(tmp_path, frames=32)


def test_create_insert_select(engine):
    engine.execute_sql("CREATE TABLE Employees (id INT, name VARCHAR(50), salary INT);")
    engine.execute_sql("INSERT INTO Employees VALUES (1, 'Alice', 75000);")
    engine.execute_sql("INSERT INTO Employees VALUES (2, 'Bob', 65000);")

    result = engine.execute_sql("SELECT * FROM Employees;")[0]

    assert result.rows == [
        (1, "Alice", 75000),
        (2, "Bob", 65000),
    ]


def test_persistence(engine):
    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (42);")

    reopened = DatabaseEngine(engine.db_dir)
    result = reopened.execute_sql("SELECT * FROM Numbers;")[0]

    assert result.rows == [(42,)]


def test_filter(engine):
    engine.execute_sql("CREATE TABLE Employees (id INT, salary INT);")
    engine.execute_sql("INSERT INTO Employees VALUES (1, 75000);")
    engine.execute_sql("INSERT INTO Employees VALUES (2, 65000);")

    result = engine.execute_sql("SELECT id FROM Employees WHERE salary > 70000;")[0]

    assert result.rows == [(1,)]


def test_explain_analyze(engine):
    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (42);")
    engine.analyze("Numbers")

    statement = __import__("src.sql.parser", fromlist=["parse_sql"]).parse_sql(
        "SELECT * FROM Numbers;"
    )[0]

    result = engine.query(statement, explain=True, execute=True)

    assert result.rows == [(42,)]
    assert result.estimated_io is not None
    assert result.actual_io is not None


def test_frame_setting(engine):
    run_command(engine, "SET frames = 16;")
    assert engine.frames == 16

    with pytest.raises(ValueError):
        engine.set_frames(3)


def test_split_multiple_statements():
    statements, remainder = split_complete_statements(
        "SELECT * FROM A; SELECT * FROM B;"
    )

    assert statements == [
        "SELECT * FROM A;",
        " SELECT * FROM B;",
    ]
    assert remainder == ""


def test_split_semicolon_inside_string():
    statements, remainder = split_complete_statements(
        "INSERT INTO Messages VALUES (1, 'Hello; World');"
    )

    assert len(statements) == 1
    assert remainder == ""


def test_split_escaped_apostrophe():
    statements, remainder = split_complete_statements(
        "INSERT INTO Messages VALUES (1, 'It''s; fine');"
    )

    assert len(statements) == 1
    assert remainder == ""


def test_split_incomplete_statement():
    statements, remainder = split_complete_statements("SELECT * FROM Employees WHERE")

    assert statements == []
    assert remainder == "SELECT * FROM Employees WHERE"


def test_multiple_sql_statements(engine):
    results = engine.execute_sql(
        "CREATE TABLE Numbers (id INT);"
        "INSERT INTO Numbers VALUES (1);"
        "INSERT INTO Numbers VALUES (2);"
        "SELECT * FROM Numbers;"
    )

    assert len(results) == 4
    assert results[-1].rows == [(1,), (2,)]


def test_invalid_insert_does_not_modify_table(engine):
    engine.execute_sql("CREATE TABLE Numbers (id INT);")

    with pytest.raises((TypeError, ValueError)):
        engine.execute_sql("INSERT INTO Numbers VALUES ('invalid');")

    result = engine.execute_sql("SELECT * FROM Numbers;")[0]
    assert result.rows == []


def test_load_csv(engine, tmp_path):
    engine.execute_sql("CREATE TABLE Employees (id INT, name VARCHAR(50));")

    csv_file = tmp_path / "employees.csv"
    csv_file.write_text(
        "1,Alice\n2,Bob\n3,Charlie\n",
        encoding="utf-8",
    )

    result = engine.load("Employees", str(csv_file))

    assert result.message == "Loaded 3 rows into Employees"
    assert engine.execute_sql("SELECT * FROM Employees;")[0].rows == [
        (1, "Alice"),
        (2, "Bob"),
        (3, "Charlie"),
    ]


def test_explain_does_not_execute(engine):
    from src.sql.parser import parse_sql

    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (42);")
    engine.analyze("Numbers")

    statement = parse_sql("SELECT * FROM Numbers;")[0]
    result = engine.query(statement, explain=True, execute=False)

    assert "Physical plan:" in result.message
    assert result.rows is None
    assert result.actual_io is None
    assert result.estimated_io is not None


def test_unsupported_query_fails_cleanly(engine):
    from src.optimizer.physical_lowering import UnsupportedPhysicalPlan

    engine.execute_sql("CREATE TABLE Numbers (id INT);")

    with pytest.raises(UnsupportedPhysicalPlan):
        engine.execute_sql("SELECT id, COUNT(*) FROM Numbers GROUP BY id;")


def test_invalid_load_command(engine):
    with pytest.raises(ValueError, match="Expected LOAD"):
        run_command(engine, "LOAD Employees invalid.csv;")


def test_invalid_explain_command(engine):
    with pytest.raises(ValueError, match="exactly one query"):
        run_command(
            engine,
            "EXPLAIN SELECT * FROM A; SELECT * FROM B;",
        )


def test_invalid_frames_command(engine):
    with pytest.raises(ValueError):
        run_command(engine, "SET frames = 3;")


def test_load_command(engine, tmp_path, capsys):
    engine.execute_sql("CREATE TABLE Numbers (id INT);")

    csv_file = tmp_path / "numbers.csv"
    csv_file.write_text("1\n2\n", encoding="utf-8")

    run_command(engine, f'LOAD Numbers FROM "{csv_file}";')

    assert "Loaded 2 rows" in capsys.readouterr().out
