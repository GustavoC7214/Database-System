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
        engine.execute_sql("SELECT id FROM Numbers WHERE id = 1 OR id = 2;")


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


def test_shell_end_to_end(tmp_path):
    """Execute SQL through the real shell process."""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    shell = repo_root / "dbshell"
    db_dir = tmp_path / "database"

    commands = (
        "CREATE TABLE Numbers (id INT);\n"
        "INSERT INTO Numbers VALUES (10);\n"
        "INSERT INTO Numbers VALUES (20);\n"
        "SELECT * FROM Numbers;\n"
        ".quit\n"
    )

    result = subprocess.run(
        [sys.executable, str(shell), "--db", str(db_dir)],
        input=commands,
        text=True,
        capture_output=True,
        cwd=repo_root,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "Created table Numbers" in result.stdout
    assert "Inserted 1 row" in result.stdout
    assert "10" in result.stdout
    assert "20" in result.stdout
    assert "Returned 2 rows" in result.stdout


def test_shell_recovers_after_error(tmp_path):
    """A failed statement must not terminate the interactive session."""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    shell = repo_root / "dbshell"

    commands = (
        "CREATE TABLE Numbers (id INT);\n"
        "INSERT INTO Numbers VALUES ('invalid');\n"
        "INSERT INTO Numbers VALUES (42);\n"
        "SELECT * FROM Numbers;\n"
        ".quit\n"
    )

    result = subprocess.run(
        [sys.executable, str(shell), "--db", str(tmp_path / "db")],
        input=commands,
        text=True,
        capture_output=True,
        cwd=repo_root,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    assert "Error:" in result.stderr
    assert "42" in result.stdout
    assert "Returned 1 rows" in result.stdout


def test_explain_reports_estimated_root_cardinality(engine):
    from src.sql.parser import parse_sql

    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (1);")
    engine.execute_sql("INSERT INTO Numbers VALUES (2);")
    engine.analyze("Numbers")

    statement = parse_sql("SELECT * FROM Numbers;")[0]
    result = engine.query(statement, explain=True, execute=False)

    assert result.estimated_rows is not None
    assert result.estimated_rows >= 0
    assert result.actual_rows is None
    assert result.execution_time_ms is None


def test_explain_analyze_reports_cardinality_and_timing(engine):
    from src.sql.parser import parse_sql

    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (1);")
    engine.execute_sql("INSERT INTO Numbers VALUES (2);")
    engine.analyze("Numbers")

    statement = parse_sql("SELECT * FROM Numbers;")[0]
    result = engine.query(statement, explain=True, execute=True)

    assert result.estimated_rows == 2
    assert result.actual_rows == 2
    assert result.execution_time_ms is not None
    assert result.execution_time_ms >= 0
    assert result.actual_io is not None


def test_filtered_query_reports_actual_root_cardinality(engine):
    from src.sql.parser import parse_sql

    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (1);")
    engine.execute_sql("INSERT INTO Numbers VALUES (2);")
    engine.execute_sql("INSERT INTO Numbers VALUES (3);")
    engine.analyze("Numbers")

    statement = parse_sql("SELECT id FROM Numbers WHERE id > 1;")[0]

    result = engine.query(statement, explain=True, execute=True)

    assert result.rows == [(2,), (3,)]
    assert result.actual_rows == 2
    assert result.counters["tuples_out"] == 2


def test_shell_displays_execution_metrics(engine, capsys):
    engine.execute_sql("CREATE TABLE Numbers (id INT);")
    engine.execute_sql("INSERT INTO Numbers VALUES (42);")
    engine.analyze("Numbers")

    run_command(
        engine,
        "EXPLAIN ANALYZE SELECT * FROM Numbers;",
    )

    output = capsys.readouterr().out

    assert "Estimated root cardinality:" in output
    assert "Actual root cardinality: 1" in output
    assert "Estimated I/O:" in output
    assert "Actual I/O:" in output
    assert "Execution time:" in output
