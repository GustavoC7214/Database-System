"""Integration tests for SQL rewrites and physical compatibility."""

from typing import cast

import pytest

from src.optimizer.physical_compatibility import check_join_compatibility
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

STATS = {
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
        definitions = {
            "Emp": [
                ("eid", "INT"),
                ("name", "VARCHAR(40)"),
                ("age", "INT"),
                ("did", "INT"),
                ("mgr", "INT"),
                ("salary", "INT"),
            ],
            "Dept": [
                ("did", "INT"),
                ("title", "VARCHAR(60)"),
                ("budget", "INT"),
            ],
            "Office": [
                ("oid", "INT"),
                ("did", "INT"),
                ("city", "VARCHAR(40)"),
            ],
        }

        self.tables = {
            name: TableMetadata(
                name=name,
                filename=f"{name}.db",
                schema=columns,
            )
            for name, columns in definitions.items()
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


def compile_one(compiler, sql, *, rewrites=True, ordering=True):
    plans = compile_optimized_sql(
        sql,
        compiler,
        STATS,
        table_columns=SCHEMA,
        enable_logical_rewrites=rewrites,
        enable_join_ordering=ordering,
    )
    assert len(plans) == 1
    return plans[0]


def walk(node):
    yield node

    for key in ("child", "left", "right"):
        child = node.get(key)
        if isinstance(child, dict):
            yield from walk(child)


def operations(plan):
    return [node["op"] for node in walk(plan)]


def normalized_join_conditions(plan):
    result = []

    for node in walk(plan):
        if node["op"] != "join":
            continue

        condition = node["condition"]

        if " AND " in condition:
            result.append(condition)
            continue

        if " = " in condition:
            left, right = condition.split(" = ", maxsplit=1)
            result.append(tuple(sorted((left.strip(), right.strip()))))
        else:
            result.append(condition)

    return sorted(result, key=str)


EXPLICIT_SQL = """
SELECT Emp.name
FROM Emp
JOIN Dept ON Emp.did = Dept.did;
"""

COMMA_SQL = """
SELECT Emp.name
FROM Emp, Dept
WHERE Emp.did = Dept.did;
"""


def test_comma_join_rewritten_to_join(compiler):
    result = compile_one(compiler, COMMA_SQL)

    assert "join" in operations(result)
    assert "cross" not in operations(result)


def test_explicit_join_optimized_with_rewrites(compiler):
    result = compile_one(compiler, EXPLICIT_SQL)

    assert "join" in operations(result)


def test_comma_and_explicit_join_predicates_equivalent(compiler):
    explicit = compile_one(compiler, EXPLICIT_SQL)
    comma = compile_one(compiler, COMMA_SQL)

    assert normalized_join_conditions(explicit) == normalized_join_conditions(comma)


def test_comma_join_without_rewrites_preserved(compiler):
    original = compiler.compile_sql(COMMA_SQL)[0]

    result = compile_one(
        compiler,
        COMMA_SQL,
        rewrites=False,
    )

    assert result == original


def test_rewrites_without_dp(compiler):
    result = compile_one(
        compiler,
        COMMA_SQL,
        ordering=False,
    )

    assert "join" in operations(result)
    assert "cross" not in operations(result)


def test_explicit_join_compatibility(compiler):
    result = compile_one(compiler, EXPLICIT_SQL)

    joins = [node for node in walk(result) if node["op"] == "join"]

    assert len(joins) == 1

    compatibility = check_join_compatibility(
        joins[0],
        table_columns=SCHEMA,
    )

    assert compatibility.supported


def test_comma_join_compatibility(compiler):
    result = compile_one(compiler, COMMA_SQL)

    joins = [node for node in walk(result) if node["op"] == "join"]

    assert len(joins) == 1

    compatibility = check_join_compatibility(
        joins[0],
        table_columns=SCHEMA,
    )

    assert compatibility.supported


def test_rewrite_pipeline_deterministic(compiler):
    first = compile_one(compiler, COMMA_SQL)
    second = compile_one(compiler, COMMA_SQL)

    assert first == second


def test_filter_preserved_after_rewrites(compiler):
    sql = """
    SELECT Emp.name
    FROM Emp, Dept
    WHERE Emp.did = Dept.did AND Emp.age > 30;
    """

    result = compile_one(compiler, sql)

    conditions = [node["condition"] for node in walk(result) if node["op"] == "select"]

    assert any("Emp.age > 30" in value for value in conditions)


def test_aliases_not_removed_by_optimizer(compiler):
    sql = """
    SELECT e.name
    FROM Emp AS e
    JOIN Dept AS d ON e.did = d.did;
    """

    result = compile_one(compiler, sql)

    renames = [node["to"] for node in walk(result) if node["op"] == "rename"]

    assert sorted(renames) == ["d", "e"]
