"""End-to-end SQL compiler and join-order integration tests."""

from copy import deepcopy
from typing import cast

import pytest

from src.optimizer.sql_pipeline import compile_optimized_sql
from src.optimizer.statistics import TableStatistics
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog, TableMetadata

SCHEMA = {
    "Emp": ["eid", "name", "age", "did", "mgr", "salary"],
    "Dept": ["did", "title", "budget"],
    "Office": ["oid", "did", "city"],
}

STATISTICS = {
    name: TableStatistics(
        table=name,
        n_tuples=rows,
        n_pages=pages,
        width=width,
    )
    for name, rows, pages, width in (
        ("Emp", 10000, 100, 48.0),
        ("Dept", 100, 5, 32.0),
        ("Office", 1000, 20, 32.0),
    )
}


class FakeCatalog:
    def __init__(self):
        self.tables = {
            name: TableMetadata(
                name=name,
                filename=f"{name}.db",
                schema=columns,
            )
            for name, columns in (
                (
                    "Emp",
                    [
                        ("eid", "INT"),
                        ("name", "VARCHAR(40)"),
                        ("age", "INT"),
                        ("did", "INT"),
                        ("mgr", "INT"),
                        ("salary", "INT"),
                    ],
                ),
                (
                    "Dept",
                    [
                        ("did", "INT"),
                        ("title", "VARCHAR(60)"),
                        ("budget", "INT"),
                    ],
                ),
                (
                    "Office",
                    [
                        ("oid", "INT"),
                        ("did", "INT"),
                        ("city", "VARCHAR(40)"),
                    ],
                ),
            )
        }

    def get_table(self, name):
        if name not in self.tables:
            raise ValueError(f"Table does not exist: {name}")
        return self.tables[name]

    def list_tables(self):
        return list(self.tables)


@pytest.fixture
def compiler():
    return SQLCompiler(SchemaCatalog(cast(Catalog, FakeCatalog())))


def compile_query(compiler, sql, *, enabled=True, stats=None):
    plans = compile_optimized_sql(
        sql,
        compiler,
        STATISTICS if stats is None else stats,
        table_columns=SCHEMA,
        enable_join_ordering=enabled,
    )
    assert len(plans) == 1
    return plans[0]


def walk(node):
    yield node

    for key in ("child", "left", "right"):
        child = node.get(key)
        if isinstance(child, dict):
            yield from walk(child)


def scan_tables(plan):
    return sorted(node["table"] for node in walk(plan) if node["op"] == "scan")


def join_conditions(plan):
    return [node["condition"] for node in walk(plan) if node["op"] == "join"]


TWO_TABLE_SQL = """
SELECT Emp.name
FROM Emp
JOIN Dept ON Emp.did = Dept.did;
"""

THREE_TABLE_SQL = """
SELECT Emp.name, Office.city
FROM Emp
JOIN Dept ON Emp.did = Dept.did
JOIN Office ON Dept.did = Office.did;
"""


def test_actual_sql_two_table_join(compiler):
    plan = compile_query(compiler, TWO_TABLE_SQL)

    assert scan_tables(plan) == ["Dept", "Emp"]
    assert len(join_conditions(plan)) == 1


def test_actual_sql_three_table_join(compiler):
    plan = compile_query(compiler, THREE_TABLE_SQL)

    assert scan_tables(plan) == ["Dept", "Emp", "Office"]
    assert len(join_conditions(plan)) == 2


def test_all_join_predicates_preserved(compiler):
    original = compile_query(
        compiler,
        THREE_TABLE_SQL,
        enabled=False,
    )
    optimized = compile_query(compiler, THREE_TABLE_SQL)

    def normalize_condition(condition: str) -> tuple[str, str]:
        """Normalize equality predicates regardless of operand order."""
        left, right = condition.split(" = ", maxsplit=1)
        return tuple(sorted((left.strip(), right.strip())))

    original_conditions = sorted(
        normalize_condition(condition) for condition in join_conditions(original)
    )

    optimized_conditions = sorted(
        normalize_condition(condition) for condition in join_conditions(optimized)
    )

    assert optimized_conditions == original_conditions


def test_projection_preserved(compiler):
    original = compile_query(
        compiler,
        THREE_TABLE_SQL,
        enabled=False,
    )
    optimized = compile_query(compiler, THREE_TABLE_SQL)

    assert original["op"] == "project"
    assert optimized["op"] == "project"
    assert original["columns"] == optimized["columns"]


def test_where_filter_preserved(compiler):
    sql = """
    SELECT Emp.name
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did
    WHERE Emp.age > 30;
    """

    original = compile_query(compiler, sql, enabled=False)
    optimized = compile_query(compiler, sql)

    original_filters = [
        node["condition"] for node in walk(original) if node["op"] == "select"
    ]
    optimized_filters = [
        node["condition"] for node in walk(optimized) if node["op"] == "select"
    ]

    assert optimized_filters == original_filters
    assert scan_tables(optimized) == ["Dept", "Emp"]


def test_comma_join_preserves_original_shape(compiler):
    sql = """
    SELECT Emp.name
    FROM Emp, Dept
    WHERE Emp.did = Dept.did;
    """

    original = compile_query(compiler, sql, enabled=False)
    optimized = compile_query(compiler, sql)

    assert optimized == original


def test_alias_join_preserves_original_shape(compiler):
    sql = """
    SELECT e.name
    FROM Emp AS e
    JOIN Dept AS d ON e.did = d.did;
    """

    original = compile_query(compiler, sql, enabled=False)
    optimized = compile_query(compiler, sql)

    assert optimized == original


def test_missing_statistics_fallback(compiler):
    original = compile_query(
        compiler,
        TWO_TABLE_SQL,
        enabled=False,
    )
    optimized = compile_query(
        compiler,
        TWO_TABLE_SQL,
        stats={"Emp": STATISTICS["Emp"]},
    )

    assert optimized == original


def test_join_ordering_disabled(compiler):
    sql = THREE_TABLE_SQL

    expected = compiler.compile_sql(sql)
    actual = compile_optimized_sql(
        sql,
        compiler,
        STATISTICS,
        table_columns=SCHEMA,
        enable_join_ordering=False,
    )

    assert actual == expected


def test_deterministic_sql_optimization(compiler):
    first = compile_query(compiler, THREE_TABLE_SQL)
    second = compile_query(compiler, THREE_TABLE_SQL)

    assert first == second


def test_multiple_sql_statements(compiler):
    source = TWO_TABLE_SQL + THREE_TABLE_SQL

    plans = compile_optimized_sql(
        source,
        compiler,
        STATISTICS,
        table_columns=SCHEMA,
    )

    assert len(plans) == 2
    assert scan_tables(plans[0]) == ["Dept", "Emp"]
    assert scan_tables(plans[1]) == ["Dept", "Emp", "Office"]


def test_statistics_not_mutated(compiler):
    original = deepcopy(STATISTICS)

    compile_query(compiler, THREE_TABLE_SQL)

    assert STATISTICS == original


def test_invalid_frames_rejected(compiler):
    with pytest.raises(ValueError):
        compile_optimized_sql(
            TWO_TABLE_SQL,
            compiler,
            STATISTICS,
            table_columns=SCHEMA,
            frames=2,
        )
