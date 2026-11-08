"""End-to-end SQL optimizer tests using real disk-backed tables."""

import json
from collections import Counter

import pytest

from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.physical_lowering import (
    UnsupportedPhysicalPlan,
    lower_physical_plan,
)
from src.optimizer.sql_pipeline import compile_optimized_sql
from src.optimizer.statistics import TableStatistics
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

FRAMES = 32

SCHEMA = {
    "Emp": ["eid", "name", "age", "did"],
    "Dept": ["did", "title"],
    "Office": ["oid", "did", "city"],
}

DATA = {
    "Emp": (
        "eid:INT,name:VARCHAR(40),age:INT,did:INT",
        [
            (1, "Alice", 35, 10),
            (2, "Bob", 24, 20),
            (3, "Charlie", 42, 10),
            (4, "David", 30, 30),
            (5, "Eve", 29, 20),
            (6, "Alice", 35, 10),
        ],
    ),
    "Dept": (
        "did:INT,title:VARCHAR(40)",
        [
            (10, "Engineering"),
            (20, "Sales"),
            (30, "Operations"),
        ],
    ),
    "Office": (
        "oid:INT,did:INT,city:VARCHAR(40)",
        [
            (100, 10, "Ottawa"),
            (101, 10, "Toronto"),
            (102, 20, "Vancouver"),
            (103, 30, "Montreal"),
        ],
    ),
}


@pytest.fixture
def database(tmp_path):
    catalog = Catalog(tmp_path)

    for name, (schema, rows) in DATA.items():
        metadata = catalog.create_table(name, schema)
        heap = HeapFile(tmp_path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()

    statistics = {
        name: TableStatistics(
            table=name,
            n_tuples=len(rows),
            n_pages=1,
            width=32.0,
        )
        for name, (_, rows) in DATA.items()
    }

    return tmp_path, catalog, statistics


def compile_and_lower(
    database,
    sql,
    *,
    ordering=True,
    rewrites=True,
):
    _, catalog, statistics = database
    compiler = SQLCompiler(SchemaCatalog(catalog))

    plans = compile_optimized_sql(
        sql,
        compiler,
        statistics,
        table_columns=SCHEMA,
        frames=FRAMES,
        enable_logical_rewrites=rewrites,
        enable_join_ordering=ordering,
    )

    assert len(plans) == 1

    return lower_physical_plan(
        plans[0],
        statistics,
        table_columns=SCHEMA,
        frames=FRAMES,
    )


def execute_plan(database, plan):
    db_dir, _, _ = database
    executor = PhysicalPlanExecutor(db_dir, frames=FRAMES)

    result = executor.execute(plan)

    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)

    return result


def execute_sql(database, sql, **kwargs):
    plan = compile_and_lower(database, sql, **kwargs)
    return execute_plan(database, plan)


def assert_equivalent(left, right):
    assert left.schema == right.schema
    assert Counter(map(tuple, left.rows)) == Counter(map(tuple, right.rows))


def test_real_table_scan(database):
    result = execute_sql(
        database,
        "SELECT * FROM Emp;",
        rewrites=False,
    )

    assert len(result.rows) == 6
    assert result.schema[0] == ("Emp.eid", "INT")


def test_real_projection(database):
    result = execute_sql(
        database,
        "SELECT name FROM Emp;",
        rewrites=False,
    )

    assert Counter(result.rows) == Counter(
        [
            ("Alice",),
            ("Bob",),
            ("Charlie",),
            ("David",),
            ("Eve",),
            ("Alice",),
        ]
    )


def test_real_filter(database):
    result = execute_sql(
        database,
        "SELECT name FROM Emp WHERE age > 30;",
        rewrites=False,
    )

    assert Counter(result.rows) == Counter(
        [
            ("Alice",),
            ("Charlie",),
            ("Alice",),
        ]
    )


def test_real_two_table_join(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    result = execute_sql(database, sql, rewrites=False)

    assert Counter(result.rows) == Counter(
        [
            ("Alice", "Engineering"),
            ("Bob", "Sales"),
            ("Charlie", "Engineering"),
            ("David", "Operations"),
            ("Eve", "Sales"),
            ("Alice", "Engineering"),
        ]
    )


def test_two_table_join_ordering_equivalence(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    original = execute_sql(
        database,
        sql,
        ordering=False,
        rewrites=False,
    )
    optimized = execute_sql(
        database,
        sql,
        ordering=True,
        rewrites=False,
    )

    assert_equivalent(original, optimized)


def test_three_table_join_ordering_equivalence(database):
    sql = """
    SELECT Emp.name, Dept.title, Office.city
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did
    JOIN Office ON Dept.did = Office.did;
    """

    original = execute_sql(
        database,
        sql,
        ordering=False,
        rewrites=False,
    )
    optimized = execute_sql(
        database,
        sql,
        ordering=True,
        rewrites=False,
    )

    assert_equivalent(original, optimized)
    assert len(optimized.rows) == 9


def test_comma_join_matches_explicit_join(database):
    explicit = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    comma = """
    SELECT Emp.name, Dept.title
    FROM Emp, Dept
    WHERE Emp.did = Dept.did;
    """

    explicit_plan = compile_and_lower(
        database,
        explicit,
        ordering=True,
        rewrites=True,
    )

    comma_plan = compile_and_lower(
        database,
        comma,
        ordering=True,
        rewrites=True,
    )

    # Both SQL forms should normalize to the same executable plan.
    assert comma_plan == explicit_plan

    explicit_result = execute_plan(database, explicit_plan)
    comma_result = execute_plan(database, comma_plan)

    assert_equivalent(explicit_result, comma_result)
    assert len(explicit_result.rows) == 6


def test_join_with_filter(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did
    WHERE Emp.age > 30;
    """

    result = execute_sql(database, sql, rewrites=False)

    assert Counter(result.rows) == Counter(
        [
            ("Alice", "Engineering"),
            ("Charlie", "Engineering"),
            ("Alice", "Engineering"),
        ]
    )


def test_physical_json_round_trip(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plan = compile_and_lower(
        database,
        sql,
        rewrites=False,
    )

    db_dir, _, _ = database
    executor = PhysicalPlanExecutor(db_dir, frames=FRAMES)

    original = executor.execute(plan)
    restored = executor.execute_json(json.dumps(plan))

    assert_equivalent(original, restored)

    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)


def test_execution_counters_available(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    result = execute_sql(database, sql, rewrites=False)

    assert result.counters["tuples_out"] == 6
    assert result.buffer_stats is not None
    assert "reads" in result.buffer_stats
    assert "writes" in result.buffer_stats


def test_unsupported_compound_filter_rejected(database):
    sql = """
    SELECT Emp.name
    FROM Emp
    WHERE Emp.age > 20 OR Emp.age < 40;
    """

    with pytest.raises(UnsupportedPhysicalPlan):
        compile_and_lower(
            database,
            sql,
            rewrites=False,
        )


def test_unsupported_alias_rejected(database):
    sql = """
    SELECT e.name
    FROM Emp AS e
    JOIN Dept AS d ON e.did = d.did;
    """

    with pytest.raises(UnsupportedPhysicalPlan):
        compile_and_lower(
            database,
            sql,
            rewrites=False,
        )


def test_physical_plan_deterministic(database):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    first = compile_and_lower(
        database,
        sql,
        rewrites=False,
    )
    second = compile_and_lower(
        database,
        sql,
        rewrites=False,
    )

    assert first == second


def test_dp_plan_lowers_and_executes_left_deep(database):
    """DP optimization produces an executable left-deep join tree."""
    sql = """
    SELECT Emp.name, Dept.title, Office.city
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did
    JOIN Office ON Dept.did = Office.did;
    """

    physical = compile_and_lower(
        database,
        sql,
        ordering=True,
        rewrites=False,
    )

    join_ops = {
        "nested_loop_join",
        "hash_join",
        "sort_merge_join",
    }

    def check_left_deep(node):
        if node["op"] in join_ops:
            assert node["right"]["op"] == "seqscan"
            check_left_deep(node["left"])
        elif "child" in node:
            check_left_deep(node["child"])

    check_left_deep(physical)

    optimized = execute_plan(database, physical)
    original = execute_sql(
        database,
        sql,
        ordering=False,
        rewrites=False,
    )

    assert_equivalent(optimized, original)
    assert len(optimized.rows) == 9
