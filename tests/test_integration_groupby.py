"""End-to-end SQL aggregation integration tests."""

import pytest

from src.integration.engine import DatabaseEngine


@pytest.fixture
def engine(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE Employees (id INT, dept INT, salary INT);")

    for employee_id, dept, salary in [
        (1, 10, 1000),
        (2, 10, 2000),
        (3, 20, 3000),
        (4, 20, 4000),
        (5, 20, 5000),
    ]:
        db.execute_sql(
            f"INSERT INTO Employees VALUES ({employee_id}, {dept}, {salary});"
        )

    return db


def rows(engine, sql):
    return engine.execute_sql(sql)[0].rows


def test_grouped_count(engine):
    result = rows(
        engine,
        "SELECT dept, COUNT(*) FROM Employees GROUP BY dept;",
    )
    assert sorted(result) == [(10, 2), (20, 3)]


def test_global_count(engine):
    result = rows(engine, "SELECT COUNT(*) FROM Employees;")
    assert result == [(5,)]


def test_grouped_sum(engine):
    result = rows(
        engine,
        "SELECT dept, SUM(salary) FROM Employees GROUP BY dept;",
    )
    assert sorted(result) == [(10, 3000), (20, 12000)]


def test_all_aggregate_functions(engine):
    result = rows(
        engine,
        "SELECT COUNT(*), SUM(salary), AVG(salary), "
        "MIN(salary), MAX(salary) FROM Employees;",
    )
    assert result == [(5, 15000, 3000.0, 1000, 5000)]


def test_aggregate_alias(engine):
    result = rows(
        engine,
        "SELECT dept, COUNT(*) AS total FROM Employees GROUP BY dept ORDER BY dept;",
    )
    assert result == [(10, 2), (20, 3)]


def test_having_count(engine):
    result = rows(
        engine,
        "SELECT dept, COUNT(*) FROM Employees GROUP BY dept HAVING COUNT(*) > 2;",
    )
    assert result == [(20, 3)]


def test_having_avg(engine):
    result = rows(
        engine,
        "SELECT dept, AVG(salary) FROM Employees "
        "GROUP BY dept HAVING AVG(salary) > 2500;",
    )
    assert result == [(20, 4000.0)]


def test_grouped_order_by_aggregate_alias(engine):
    result = rows(
        engine,
        "SELECT dept, SUM(salary) AS total "
        "FROM Employees GROUP BY dept ORDER BY total DESC;",
    )
    assert result == [(20, 12000), (10, 3000)]


def test_empty_global_count(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE EmptyNumbers (id INT);")

    assert rows(db, "SELECT COUNT(*) FROM EmptyNumbers;") == [(0,)]


def test_empty_grouped_count(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE EmptyNumbers (id INT);")

    assert (
        rows(
            db,
            "SELECT id, COUNT(*) FROM EmptyNumbers GROUP BY id;",
        )
        == []
    )
