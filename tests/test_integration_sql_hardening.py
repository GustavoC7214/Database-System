"""Regression tests for SQL integration and schema validation."""

import pytest

from src.integration.engine import DatabaseEngine


@pytest.fixture
def engine(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)

    db.execute_sql("CREATE TABLE A (id INT, value INT);")
    db.execute_sql("CREATE TABLE B (id INT, value INT);")
    db.execute_sql("CREATE TABLE Names (name VARCHAR(20));")

    for identifier, value in [(1, 10), (2, 20), (3, 20)]:
        db.execute_sql(f"INSERT INTO A VALUES ({identifier}, {value});")

    for identifier, value in [(2, 20), (4, 40)]:
        db.execute_sql(f"INSERT INTO B VALUES ({identifier}, {value});")

    db.execute_sql("INSERT INTO Names VALUES ('Alice');")
    return db


@pytest.mark.parametrize(
    "operation",
    ["UNION", "UNION ALL", "INTERSECT", "EXCEPT"],
)
def test_set_operation_rejects_different_column_counts(engine, operation):
    with pytest.raises(ValueError, match="same number of columns"):
        engine.execute_sql(f"SELECT id FROM A {operation} SELECT id, value FROM B;")


@pytest.mark.parametrize(
    "operation",
    ["UNION", "UNION ALL", "INTERSECT", "EXCEPT"],
)
def test_set_operation_rejects_incompatible_types(engine, operation):
    with pytest.raises(
        ValueError,
        match=rf"{operation} column 1 has incompatible types",
    ):
        engine.execute_sql(f"SELECT id FROM A {operation} SELECT name FROM Names;")


@pytest.mark.parametrize(
    "operation",
    ["UNION", "UNION ALL", "INTERSECT", "EXCEPT"],
)
def test_set_operation_uses_left_column_names(engine, operation):
    result = engine.execute_sql(
        f"SELECT id AS left_id FROM A {operation} SELECT id AS right_id FROM B;"
    )[0]

    assert result.columns == ["left_id"]


def test_group_by_having_order_by_and_limit(engine):
    result = engine.execute_sql(
        "SELECT value, COUNT(*) AS total "
        "FROM A "
        "GROUP BY value "
        "HAVING COUNT(*) >= 1 "
        "ORDER BY total DESC "
        "LIMIT 1;"
    )[0]

    assert result.columns == ["A.value", "total"]
    assert result.rows == [(20, 2)]


def test_group_by_with_where_and_sum(engine):
    result = engine.execute_sql(
        "SELECT value, SUM(id) AS total "
        "FROM A "
        "WHERE id > 1 "
        "GROUP BY value "
        "ORDER BY value;"
    )[0]

    assert result.rows == [(20, 5)]


def test_query_after_rejected_set_operation(engine):
    with pytest.raises(ValueError):
        engine.execute_sql("SELECT id FROM A UNION ALL SELECT id, value FROM B;")

    result = engine.execute_sql("SELECT COUNT(*) FROM A;")[0]
    assert result.rows == [(3,)]


def test_empty_grouped_aggregate(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE EmptyData (id INT);")

    result = db.execute_sql("SELECT id, SUM(id) FROM EmptyData GROUP BY id;")[0]

    assert result.rows == []


def test_aggregate_output_columns(engine):
    result = engine.execute_sql(
        "SELECT COUNT(*) AS total, SUM(value) AS amount FROM A;"
    )[0]

    assert result.columns == ["total", "amount"]
    assert result.rows == [(3, 50)]
