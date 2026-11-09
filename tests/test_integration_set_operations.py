"""End-to-end SQL set-operation integration tests."""

import pytest

from src.integration.engine import DatabaseEngine


@pytest.fixture
def engine(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)

    db.execute_sql("CREATE TABLE LeftNumbers (id INT);")
    db.execute_sql("CREATE TABLE RightNumbers (id INT);")

    for value in [1, 2, 2, 3]:
        db.execute_sql(f"INSERT INTO LeftNumbers VALUES ({value});")

    for value in [2, 3, 3, 4]:
        db.execute_sql(f"INSERT INTO RightNumbers VALUES ({value});")

    return db


def rows(engine, sql):
    return engine.execute_sql(sql)[0].rows


def test_union_removes_duplicates(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers UNION SELECT id FROM RightNumbers;",
    )
    assert sorted(result) == [(1,), (2,), (3,), (4,)]


def test_union_all_preserves_duplicates(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers UNION ALL SELECT id FROM RightNumbers;",
    )
    assert sorted(result) == [(1,), (2,), (2,), (2,), (3,), (3,), (3,), (4,)]


def test_intersect_returns_common_distinct_rows(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers INTERSECT SELECT id FROM RightNumbers;",
    )
    assert sorted(result) == [(2,), (3,)]


def test_except_returns_left_only_rows(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers EXCEPT SELECT id FROM RightNumbers;",
    )
    assert result == [(1,)]


def test_except_direction_matters(engine):
    result = rows(
        engine,
        "SELECT id FROM RightNumbers EXCEPT SELECT id FROM LeftNumbers;",
    )
    assert result == [(4,)]


def test_union_all_with_empty_input(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE A (id INT);")
    db.execute_sql("CREATE TABLE B (id INT);")
    db.execute_sql("INSERT INTO A VALUES (10);")

    result = rows(
        db,
        "SELECT id FROM A UNION ALL SELECT id FROM B;",
    )
    assert result == [(10,)]


def test_union_all_preserves_left_schema(engine):
    result = engine.execute_sql(
        "SELECT id AS first_id FROM LeftNumbers "
        "UNION ALL "
        "SELECT id AS second_id FROM RightNumbers;"
    )[0]

    assert len(result.rows) == 8
    assert sorted(result.rows) == [
        (1,),
        (2,),
        (2,),
        (2,),
        (3,),
        (3,),
        (3,),
        (4,),
    ]
    assert result.columns == ["first_id"]


def test_union_with_filtered_inputs(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers WHERE id > 1 "
        "UNION "
        "SELECT id FROM RightNumbers WHERE id > 3;",
    )
    assert sorted(result) == [(2,), (3,), (4,)]


def test_intersect_with_no_common_rows(tmp_path):
    db = DatabaseEngine(tmp_path, frames=16)
    db.execute_sql("CREATE TABLE A (id INT);")
    db.execute_sql("CREATE TABLE B (id INT);")
    db.execute_sql("INSERT INTO A VALUES (1);")
    db.execute_sql("INSERT INTO B VALUES (2);")

    result = rows(
        db,
        "SELECT id FROM A INTERSECT SELECT id FROM B;",
    )
    assert result == []


def test_except_with_identical_inputs(engine):
    result = rows(
        engine,
        "SELECT id FROM LeftNumbers EXCEPT SELECT id FROM LeftNumbers;",
    )
    assert result == []
