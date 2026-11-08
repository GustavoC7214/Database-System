"""Integration tests for Module 3 SQL and Module 4 rewrites."""

from copy import deepcopy
from typing import cast

import pytest

from src.optimizer.pipeline import optimize_logical_plan
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog, TableMetadata

SCHEMA = {
    "Emp": ["eid", "name", "age", "did", "mgr", "salary"],
    "Dept": ["did", "title", "budget"],
    "Office": ["oid", "did", "city"],
}


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
                    ("mgr", "INT"),
                    ("salary", "INT"),
                ],
            ),
            "Dept": TableMetadata(
                name="Dept",
                filename="Dept.db",
                schema=[
                    ("did", "INT"),
                    ("title", "VARCHAR(60)"),
                    ("budget", "INT"),
                ],
            ),
            "Office": TableMetadata(
                name="Office",
                filename="Office.db",
                schema=[
                    ("oid", "INT"),
                    ("did", "INT"),
                    ("city", "VARCHAR(40)"),
                ],
            ),
        }

    def get_table(self, name: str) -> TableMetadata:
        if name not in self.tables:
            raise ValueError(f"Table does not exist: {name}")
        return self.tables[name]

    def list_tables(self) -> list[str]:
        return list(self.tables)


@pytest.fixture
def compiler() -> SQLCompiler:
    return SQLCompiler(SchemaCatalog(cast(Catalog, FakeCatalog())))


def compile_one(compiler: SQLCompiler, sql: str) -> dict:
    plans = compiler.compile_sql(sql)
    assert len(plans) == 1
    return plans[0]


def optimize(plan: dict) -> dict:
    return optimize_logical_plan(plan, table_columns=SCHEMA)


def walk(plan: dict):
    yield plan

    if "child" in plan:
        yield from walk(plan["child"])

    if "left" in plan:
        yield from walk(plan["left"])

    if "right" in plan:
        yield from walk(plan["right"])


def test_simple_select_compiler_integration(compiler):
    plan = compile_one(
        compiler,
        "SELECT name, age FROM Emp WHERE age > 30;",
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["columns"] == ["Emp.name", "Emp.age"]
    assert result["child"]["op"] == "select"
    assert result["child"]["condition"] == "Emp.age > 30"


def test_compiled_filter_preserves_required_column(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp WHERE age > 30;",
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["columns"] == ["Emp.name"]

    selection = result["child"]
    assert selection["op"] == "select"

    pushed = selection["child"]
    assert pushed["op"] == "project"
    assert "Emp.name" in pushed["columns"]
    assert "Emp.age" in pushed["columns"]


def test_compiled_alias_filter_pushdown(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name FROM Emp e WHERE e.age > 30;",
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["child"]["op"] == "rename"
    assert result["child"]["to"] == "e"

    selection = result["child"]["child"]
    assert selection["op"] == "select"
    assert selection["condition"] == "Emp.age > 30"


def test_compiled_explicit_join(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, d.title FROM Emp e "
        "JOIN Dept d ON e.did = d.did "
        "WHERE d.budget > 1000;",
    )

    result = optimize(plan)

    assert result["op"] == "project"
    assert result["child"]["op"] == "join"
    assert result["child"]["condition"] == "e.did = d.did"

    right = result["child"]["right"]

    # Projection pushdown may insert a projection above rename.
    assert right["op"] == "project"
    assert right["columns"] == ["d.did", "d.title"]

    renamed = right["child"]
    assert renamed["op"] == "rename"
    assert renamed["to"] == "d"

    selection = renamed["child"]
    assert selection["op"] == "select"
    assert selection["condition"] == "Dept.budget > 1000"

    assert selection["child"]["op"] == "scan"
    assert selection["child"]["table"] == "Dept"


def test_compiled_join_keeps_both_inputs(compiler):
    plan = compile_one(
        compiler,
        "SELECT Emp.name, Dept.title FROM Emp JOIN Dept ON Emp.did = Dept.did;",
    )

    result = optimize(plan)

    joins = [node for node in walk(result) if node["op"] == "join"]
    scans = [node for node in walk(result) if node["op"] == "scan"]

    assert len(joins) == 1
    assert {node["table"] for node in scans} == {"Emp", "Dept"}


def test_compiled_select_star_preserves_outputs(compiler):
    plan = compile_one(compiler, "SELECT * FROM Emp;")

    result = optimize(plan)

    assert result == plan


def test_compiled_plan_is_not_mutated(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp WHERE age > 30;",
    )
    original = deepcopy(plan)

    optimize(plan)

    assert plan == original


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM Emp WHERE age > 30;",
        "SELECT e.name FROM Emp e WHERE e.age > 30;",
        (
            "SELECT e.name, d.title FROM Emp e "
            "JOIN Dept d ON e.did = d.did "
            "WHERE d.budget > 1000;"
        ),
        "SELECT * FROM Emp;",
    ],
)
def test_compiled_optimization_is_deterministic(compiler, sql):
    plan = compile_one(compiler, sql)

    assert optimize(plan) == optimize(plan)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM Emp WHERE age > 30;",
        "SELECT e.name FROM Emp e WHERE e.age > 30;",
        (
            "SELECT e.name, d.title FROM Emp e "
            "JOIN Dept d ON e.did = d.did "
            "WHERE d.budget > 1000;"
        ),
    ],
)
def test_compiled_optimization_is_idempotent(compiler, sql):
    plan = compile_one(compiler, sql)

    once = optimize(plan)
    twice = optimize(once)

    assert once == twice
