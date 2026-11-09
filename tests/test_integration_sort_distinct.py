"""End-to-end SQL integration tests for sorting and duplicate elimination."""

import pytest

from src.integration.engine import DatabaseEngine


@pytest.fixture
def engine(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE Numbers (id INT, category INT);")

    for row in [
        (3, 20),
        (1, 10),
        (2, 20),
        (1, 10),
        (4, 30),
    ]:
        db.execute_sql(f"INSERT INTO Numbers VALUES ({row[0]}, {row[1]});")

    return db


def query_rows(engine, sql):
    return engine.execute_sql(sql)[0].rows


def test_order_by_ascending(engine):
    rows = query_rows(
        engine,
        "SELECT id FROM Numbers ORDER BY id ASC;",
    )

    assert rows == [(1,), (1,), (2,), (3,), (4,)]


def test_order_by_descending(engine):
    rows = query_rows(
        engine,
        "SELECT id FROM Numbers ORDER BY id DESC;",
    )

    assert rows == [(4,), (3,), (2,), (1,), (1,)]


def test_distinct(engine):
    rows = query_rows(
        engine,
        "SELECT DISTINCT category FROM Numbers;",
    )

    assert set(rows) == {(10,), (20,), (30,)}
    assert len(rows) == 3


def test_distinct_order_by(engine):
    rows = query_rows(
        engine,
        "SELECT DISTINCT category FROM Numbers ORDER BY category DESC;",
    )

    assert rows == [(30,), (20,), (10,)]


def test_order_by_with_limit(engine):
    rows = query_rows(
        engine,
        "SELECT id FROM Numbers ORDER BY id DESC LIMIT 2;",
    )

    assert rows == [(4,), (3,)]


def test_order_by_non_projected_column(engine):
    rows = query_rows(
        engine,
        "SELECT id FROM Numbers ORDER BY category ASC, id ASC;",
    )

    assert rows == [(1,), (1,), (2,), (3,), (4,)]


def test_distinct_with_limit(engine):
    rows = query_rows(
        engine,
        "SELECT DISTINCT id FROM Numbers ORDER BY id ASC LIMIT 3;",
    )

    assert rows == [(1,), (2,), (3,)]
