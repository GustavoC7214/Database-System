"""Tests for canonical Module 3 logical-plan generation."""

from typing import cast

import pytest

from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler, plan_json
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


def compile_one(compiler: SQLCompiler, sql: str):
    plans = compiler.compile_sql(sql)
    assert len(plans) == 1
    return plans[0]


def test_simple_select(compiler):
    plan = compile_one(
        compiler,
        "SELECT name, age FROM Emp WHERE age > 30;",
    )

    assert plan == {
        "op": "project",
        "columns": ["Emp.name", "Emp.age"],
        "child": {
            "op": "select",
            "condition": "Emp.age > 30",
            "child": {
                "op": "scan",
                "table": "Emp",
            },
        },
    }


def test_scan_and_alias(compiler):
    plan = compile_one(compiler, "SELECT e.name FROM Emp e;")

    assert plan["child"] == {
        "op": "rename",
        "to": "e",
        "child": {"op": "scan", "table": "Emp"},
    }


def test_join_and_where(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, d.title FROM Emp e "
        "JOIN Dept d ON e.did = d.did "
        "WHERE d.budget > 1000;",
    )

    assert plan == {
        "op": "project",
        "columns": ["e.name", "d.title"],
        "child": {
            "op": "select",
            "condition": "d.budget > 1000",
            "child": {
                "op": "join",
                "condition": "e.did = d.did",
                "left": {
                    "op": "rename",
                    "to": "e",
                    "child": {"op": "scan", "table": "Emp"},
                },
                "right": {
                    "op": "rename",
                    "to": "d",
                    "child": {"op": "scan", "table": "Dept"},
                },
            },
        },
    }


def test_self_join(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, m.name FROM Emp e JOIN Emp m ON e.mgr = m.eid;",
    )

    join = plan["child"]
    assert join["op"] == "join"
    assert join["left"]["to"] == "e"
    assert join["right"]["to"] == "m"


def test_cross_product(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, d.title FROM Emp e, Dept d;",
    )

    assert plan["child"]["op"] == "cross"
    assert plan["child"]["left"]["op"] == "rename"
    assert plan["child"]["right"]["op"] == "rename"


def test_three_table_cross_order(compiler):
    plan = compile_one(
        compiler,
        "SELECT * FROM Emp e, Dept d, Office o;",
    )

    assert plan["child"]["op"] == "cross"
    assert plan["child"]["left"]["op"] == "cross"
    assert len(plan["columns"]) == 12
    assert plan["columns"][0] == "e.eid"
    assert plan["columns"][-1] == "o.city"


def test_select_distinct(compiler):
    plan = compile_one(
        compiler,
        "SELECT DISTINCT did FROM Emp;",
    )

    assert plan["op"] == "distinct"
    assert plan["child"]["op"] == "project"


def test_where_boolean_condition(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp WHERE age > 20 AND salary >= 50000;",
    )

    condition = plan["child"]["condition"]
    assert condition == ("(Emp.age > 20 AND Emp.salary >= 50000)")


def test_string_literal_escaping(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp WHERE name = 'O''Brien';",
    )

    assert plan["child"]["condition"] == "Emp.name = 'O''Brien'"


def test_group_by_and_having(compiler):
    plan = compile_one(
        compiler,
        "SELECT did, COUNT(*) AS n, AVG(salary) AS avg_sal "
        "FROM Emp WHERE age > 25 GROUP BY did "
        "HAVING COUNT(*) > 5 ORDER BY n DESC LIMIT 10;",
    )

    assert plan["op"] == "limit"
    assert plan["count"] == 10

    sort = plan["child"]
    assert sort["op"] == "sort"
    assert sort["keys"] == [["n", "desc"]]

    project = sort["child"]
    assert project["op"] == "project"
    assert project["columns"] == ["Emp.did", "n", "avg_sal"]

    having = project["child"]
    assert having["op"] == "select"
    assert having["condition"] == "n > 5"

    group = having["child"]
    assert group["op"] == "group_by"
    assert group["keys"] == ["Emp.did"]
    assert group["aggregates"] == [
        ["count", "*", "n"],
        ["avg", "Emp.salary", "avg_sal"],
    ]

    where = group["child"]
    assert where["op"] == "select"
    assert where["condition"] == "Emp.age > 25"


def test_global_count(compiler):
    plan = compile_one(
        compiler,
        "SELECT COUNT(*) AS n FROM Emp;",
    )

    group = plan["child"]
    assert group["op"] == "group_by"
    assert group["keys"] == []
    assert group["aggregates"] == [["count", "*", "n"]]


def test_group_by_without_aggregate(compiler):
    plan = compile_one(
        compiler,
        "SELECT did FROM Emp GROUP BY did;",
    )

    assert plan["child"]["op"] == "group_by"
    assert plan["child"]["keys"] == ["Emp.did"]
    assert plan["child"]["aggregates"] == []


def test_having_alias(compiler):
    plan = compile_one(
        compiler,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did HAVING n > 5;",
    )

    assert plan["child"]["condition"] == "n > 5"


def test_order_by_nonselected_column(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp ORDER BY age DESC;",
    )

    assert plan == {
        "op": "project",
        "columns": ["Emp.name"],
        "child": {
            "op": "sort",
            "keys": [["Emp.age", "desc"]],
            "child": {
                "op": "scan",
                "table": "Emp",
            },
        },
    }


def test_limit_zero(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp LIMIT 0;",
    )

    assert plan["op"] == "limit"
    assert plan["count"] == 0


def test_derived_table(compiler):
    plan = compile_one(
        compiler,
        "SELECT t.did FROM (SELECT did FROM Emp) AS t;",
    )

    rename = plan["child"]
    assert rename["op"] == "rename"
    assert rename["to"] == "t"
    assert rename["child"]["op"] == "project"


def test_derived_table_join(compiler):
    plan = compile_one(
        compiler,
        "SELECT t.did, d.title FROM "
        "(SELECT did FROM Emp) AS t "
        "JOIN Dept d ON t.did = d.did;",
    )

    join = plan["child"]
    assert join["op"] == "join"
    assert join["left"]["op"] == "rename"
    assert join["left"]["to"] == "t"


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("UNION", "union"),
        ("UNION ALL", "union_all"),
        ("INTERSECT", "intersect"),
        ("EXCEPT", "except"),
    ],
)
def test_set_operations(compiler, operator, expected):
    plan = compile_one(
        compiler,
        f"SELECT eid FROM Emp {operator} SELECT did FROM Dept;",
    )

    assert plan["op"] == expected
    assert plan["left"]["op"] == "project"
    assert plan["right"]["op"] == "project"


def test_left_associative_set_operations(compiler):
    plan = compile_one(
        compiler,
        "SELECT eid FROM Emp UNION SELECT did FROM Dept EXCEPT SELECT oid FROM Office;",
    )

    assert plan["op"] == "except"
    assert plan["left"]["op"] == "union"


def test_multiple_queries(compiler):
    plans = compiler.compile_sql("SELECT name FROM Emp;SELECT title FROM Dept;")

    assert len(plans) == 2
    assert plans[0]["columns"] == ["Emp.name"]
    assert plans[1]["columns"] == ["Dept.title"]


def test_json_serialization(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp;",
    )

    import json

    assert json.loads(plan_json(plan)) == plan


# ------------------------------------------------------------
# Stage 3.1: Compiler correctness hardening
# ------------------------------------------------------------


def test_projection_alias_preserves_source(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee FROM Emp;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == ["Emp.name"]
    assert plan["aliases"] == {"employee": "Emp.name"}


def test_multiple_projection_aliases(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee, age AS years FROM Emp;",
    )

    assert plan["columns"] == ["Emp.name", "Emp.age"]
    assert plan["aliases"] == {
        "employee": "Emp.name",
        "years": "Emp.age",
    }


def test_unaliased_projection_has_no_alias_mapping(compiler):
    plan = compile_one(
        compiler,
        "SELECT name, age FROM Emp;",
    )

    assert "aliases" not in plan


def test_order_by_selected_column_stays_after_projection(compiler):
    plan = compile_one(
        compiler,
        "SELECT name, age FROM Emp ORDER BY age DESC;",
    )

    assert plan["op"] == "sort"
    assert plan["keys"] == [["Emp.age", "desc"]]
    assert plan["child"]["op"] == "project"


def test_order_by_alias_stays_after_projection(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee FROM Emp ORDER BY employee ASC;",
    )

    assert plan["op"] == "sort"
    assert plan["keys"] == [["employee", "asc"]]
    assert plan["child"]["aliases"] == {
        "employee": "Emp.name",
    }


def test_order_by_nonselected_column_with_limit(compiler):
    plan = compile_one(
        compiler,
        "SELECT name FROM Emp ORDER BY age DESC LIMIT 5;",
    )

    assert plan["op"] == "limit"
    assert plan["count"] == 5
    assert plan["child"]["op"] == "project"
    assert plan["child"]["child"]["op"] == "sort"


def test_order_by_nonselected_column_with_alias(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee FROM Emp ORDER BY age;",
    )

    assert plan["op"] == "project"
    assert plan["aliases"] == {"employee": "Emp.name"}
    assert plan["child"]["op"] == "sort"
    assert plan["child"]["keys"] == [["Emp.age", "asc"]]


def test_distinct_nonselected_sort_key_rejected(compiler):
    with pytest.raises(ValueError, match="DISTINCT"):
        compile_one(
            compiler,
            "SELECT DISTINCT name FROM Emp ORDER BY age;",
        )


def test_repeated_count_aggregate_reused(compiler):
    plan = compile_one(
        compiler,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did HAVING COUNT(*) > 5;",
    )

    project = plan
    having = project["child"]
    group = having["child"]

    assert project["columns"] == ["Emp.did", "n"]
    assert having["condition"] == "n > 5"
    assert group["aggregates"] == [["count", "*", "n"]]


def test_having_aggregate_alias_matches_group_output(compiler):
    plan = compile_one(
        compiler,
        "SELECT did, SUM(salary) AS total FROM Emp GROUP BY did HAVING total > 100000;",
    )

    project = plan
    having = project["child"]
    group = having["child"]

    assert project["columns"] == ["Emp.did", "total"]
    assert having["condition"] == "total > 100000"
    assert group["aggregates"] == [["sum", "Emp.salary", "total"]]


def test_having_aggregate_not_in_select(compiler):
    plan = compile_one(
        compiler,
        "SELECT did FROM Emp GROUP BY did HAVING COUNT(*) > 2;",
    )

    group = plan["child"]["child"]

    assert plan["child"]["condition"] == "count_star > 2"
    assert group["aggregates"] == [["count", "*", "count_star"]]


def test_order_by_nonselected_group_key(compiler):
    plan = compile_one(
        compiler,
        "SELECT COUNT(*) AS n FROM Emp GROUP BY did ORDER BY did;",
    )

    assert plan["op"] == "project"
    assert plan["child"]["op"] == "sort"
    assert plan["child"]["keys"] == [["Emp.did", "asc"]]
    assert plan["child"]["child"]["op"] == "group_by"


# ------------------------------------------------------------
# Stage 5.1: Final compiler correctness regression tests
# ------------------------------------------------------------


def test_mixed_order_by_keys_before_projection(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee FROM Emp ORDER BY age DESC, employee ASC;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == ["Emp.name"]
    assert plan["aliases"] == {"employee": "Emp.name"}

    sort = plan["child"]
    assert sort["op"] == "sort"
    assert sort["keys"] == [
        ["Emp.age", "desc"],
        ["Emp.name", "asc"],
    ]
    assert sort["child"] == {
        "op": "scan",
        "table": "Emp",
    }


def test_sort_unaliased_reference_to_aliased_column(compiler):
    plan = compile_one(
        compiler,
        "SELECT name AS employee FROM Emp ORDER BY name ASC;",
    )

    assert plan["op"] == "project"
    assert plan["child"]["op"] == "sort"
    assert plan["child"]["keys"] == [["Emp.name", "asc"]]


def test_derived_table_alias_source_is_preserved(compiler):
    plan = compile_one(
        compiler,
        "SELECT d.employee FROM (SELECT name AS employee FROM Emp) AS d;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == ["d.employee"]

    rename = plan["child"]
    assert rename["op"] == "rename"
    assert rename["to"] == "d"

    inner = rename["child"]
    assert inner["op"] == "project"
    assert inner["columns"] == ["Emp.name"]
    assert inner["aliases"] == {"employee": "Emp.name"}


def test_derived_table_alias_in_where(compiler):
    plan = compile_one(
        compiler,
        "SELECT d.employee FROM "
        "(SELECT name AS employee FROM Emp) AS d "
        "WHERE d.employee = 'Alice';",
    )

    assert plan["op"] == "project"

    selection = plan["child"]
    assert selection["op"] == "select"
    assert selection["condition"] == "d.employee = 'Alice'"

    assert selection["child"]["op"] == "rename"
    assert selection["child"]["child"]["aliases"] == {
        "employee": "Emp.name",
    }


def test_repeated_aggregate_aliases_preserve_both_outputs(compiler):
    plan = compile_one(
        compiler,
        "SELECT COUNT(*) AS total, COUNT(*) AS n FROM Emp;",
    )

    assert plan["op"] == "project"

    # The underlying aggregate should be calculated once.
    group = plan["child"]
    assert group["op"] == "group_by"
    assert len(group["aggregates"]) == 1
    assert group["aggregates"][0][:2] == ["count", "*"]

    # Both output names must be recoverable from the plan.
    assert plan["columns"] == ["total", "n"] or (plan.get("outputs") == ["total", "n"])


def test_duplicate_aggregate_alias_in_derived_table(compiler):
    plan = compile_one(
        compiler,
        "SELECT d.n FROM (SELECT COUNT(*) AS total, COUNT(*) AS n FROM Emp) AS d;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == ["d.n"]

    inner = plan["child"]["child"]
    assert inner["op"] == "project"

    # The derived table must expose an output named n.
    assert "n" in inner["columns"] or "n" in inner.get("outputs", [])


def test_grouped_distinct_does_not_add_redundant_node(compiler):
    plan = compile_one(
        compiler,
        "SELECT DISTINCT did, COUNT(*) AS n FROM Emp GROUP BY did;",
    )
    assert plan["op"] == "project"
    assert plan["child"]["op"] == "group_by"
    assert plan["child"]["keys"] == ["Emp.did"]


def test_implicit_grouping_distinct_does_not_add_redundant_node(compiler):
    plan = compile_one(compiler, "SELECT DISTINCT COUNT(*) AS n FROM Emp;")
    assert plan["op"] == "project"
    assert plan["child"]["op"] == "group_by"


def test_multiple_aliases_of_same_aggregate_keep_positions(compiler):
    plan = compile_one(
        compiler,
        "SELECT COUNT(*) AS total, COUNT(*) AS n FROM Emp;",
    )
    assert plan["columns"] == ["total", "total"]
    assert plan["outputs"] == ["total", "n"]
    assert plan["aliases"] == {"n": "total"}


def test_four_table_comma_join_chain(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, d.title, o.city, m.name "
        "FROM Emp e, Dept d, Office o, Emp m "
        "WHERE e.did = d.did AND d.did = o.did "
        "AND e.mgr = m.eid;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == [
        "e.name",
        "d.title",
        "o.city",
        "m.name",
    ]

    where = plan["child"]
    assert where["op"] == "select"
    assert "e.did = d.did" in where["condition"]
    assert "d.did = o.did" in where["condition"]
    assert "e.mgr = m.eid" in where["condition"]

    root = where["child"]
    assert root["op"] == "cross"
    assert root["right"]["to"] == "m"

    third = root["left"]
    assert third["op"] == "cross"
    assert third["right"]["to"] == "o"

    second = third["left"]
    assert second["op"] == "cross"
    assert second["left"]["to"] == "e"
    assert second["right"]["to"] == "d"


def test_four_table_explicit_join_chain(compiler):
    plan = compile_one(
        compiler,
        "SELECT e.name, d.title, o.city, m.name "
        "FROM Emp e "
        "JOIN Dept d ON e.did = d.did "
        "JOIN Office o ON d.did = o.did "
        "JOIN Emp m ON e.mgr = m.eid;",
    )

    assert plan["op"] == "project"
    assert plan["columns"] == [
        "e.name",
        "d.title",
        "o.city",
        "m.name",
    ]

    root = plan["child"]
    assert root["op"] == "join"
    assert root["condition"] == "e.mgr = m.eid"
    assert root["right"]["to"] == "m"

    third = root["left"]
    assert third["op"] == "join"
    assert third["condition"] == "d.did = o.did"
    assert third["right"]["to"] == "o"

    second = third["left"]
    assert second["op"] == "join"
    assert second["condition"] == "e.did = d.did"
    assert second["left"]["to"] == "e"
    assert second["right"]["to"] == "d"
