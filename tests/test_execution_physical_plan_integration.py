"""End-to-end tests for JSON physical plans over disk-backed tables."""

import json

import pytest

from src.execution.plan_executor import PhysicalPlanExecutor
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


@pytest.fixture
def database_dir(tmp_path):
    catalog = Catalog(tmp_path)

    tables = {
        "Employees": (
            "id:INT,department:INT,name:VARCHAR(30),salary:INT",
            [
                (1, 10, "Alice", 70000),
                (2, 20, "Bob", 45000),
                (3, 10, "Charlie", 80000),
                (4, 30, "David", 55000),
                (5, 20, "Eve", 60000),
            ],
        ),
        "Departments": (
            "id:INT,label:VARCHAR(30)",
            [
                (10, "Engineering"),
                (20, "Sales"),
                (30, "Operations"),
            ],
        ),
        "NumbersA": (
            "value:INT",
            [(1,), (2,), (2,), (3,), (4,)],
        ),
        "NumbersB": (
            "value:INT",
            [(2,), (3,), (3,), (5,)],
        ),
    }

    for name, (schema, rows) in tables.items():
        metadata = catalog.create_table(name, schema)
        heap = HeapFile(tmp_path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()

    return tmp_path


def scan(table):
    return {"op": "SeqScan", "table": table}


def assert_clean(executor):
    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)


def test_scan_from_json(database_dir):
    executor = PhysicalPlanExecutor(database_dir)

    result = executor.execute_json(json.dumps(scan("Employees")))

    assert len(result.rows) == 5
    assert result.rows[0] == (1, 10, "Alice", 70000)
    assert result.schema[0] == ("Employees.id", "INT")
    assert result.counters["tuples_out"] == 5
    assert_clean(executor)


def test_filter_project_limit(database_dir):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "Limit",
        "count": 2,
        "child": {
            "op": "Project",
            "columns": ["Employees.name"],
            "child": {
                "op": "Filter",
                "column": "Employees.salary",
                "comparison": ">",
                "value": 50000,
                "child": scan("Employees"),
            },
        },
    }

    result = executor.execute(plan)

    assert result.rows == [("Alice",), ("Charlie",)]
    assert result.schema == [("Employees.name", "VARCHAR(30)")]
    assert_clean(executor)


def test_sort(database_dir):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "Sort",
        "keys": [["Employees.salary", "DESC"]],
        "child": scan("Employees"),
    }

    result = executor.execute(plan)

    assert [row[0] for row in result.rows] == [3, 1, 5, 4, 2]
    assert_clean(executor)


@pytest.mark.parametrize("mode", ["sort", "hash"])
def test_group_by(database_dir, mode):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "GroupBy",
        "mode": mode,
        "keys": ["Employees.department"],
        "aggregates": [
            ["count", "*"],
            ["sum", "Employees.salary"],
        ],
        "child": scan("Employees"),
    }

    result = executor.execute(plan)

    assert sorted(result.rows) == [
        (10, 2, 150000),
        (20, 2, 105000),
        (30, 1, 55000),
    ]
    assert_clean(executor)


@pytest.mark.parametrize(
    "join_type",
    [
        "NestedLoopJoin",
        "SortMergeJoin",
        "GraceHashJoin",
    ],
)
def test_join_algorithms(database_dir, join_type):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": join_type,
        "left_key": "Employees.department",
        "right_key": "Departments.id",
        "left": scan("Employees"),
        "right": scan("Departments"),
    }

    result = executor.execute(plan)

    assert len(result.rows) == 5

    matches = {row[2]: row[5] for row in result.rows}

    assert matches == {
        "Alice": "Engineering",
        "Bob": "Sales",
        "Charlie": "Engineering",
        "David": "Operations",
        "Eve": "Sales",
    }
    assert_clean(executor)


@pytest.mark.parametrize(
    "join_type",
    [
        "nested_loop_join",
        "sort_merge_join",
        "hash_join",
    ],
)
def test_join_with_qualified_condition(database_dir, join_type):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": join_type,
        "condition": "Employees.department = Departments.id",
        "left": scan("Employees"),
        "right": scan("Departments"),
    }

    result = executor.execute(plan)

    matches = {row[2]: row[5] for row in result.rows}

    assert matches == {
        "Alice": "Engineering",
        "Bob": "Sales",
        "Charlie": "Engineering",
        "David": "Operations",
        "Eve": "Sales",
    }
    assert_clean(executor)


@pytest.mark.parametrize(
    "join_type",
    [
        "nested_loop_join",
        "sort_merge_join",
        "hash_join",
    ],
)
def test_join_with_reversed_condition(database_dir, join_type):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": join_type,
        "condition": "Departments.id = Employees.department",
        "left": scan("Employees"),
        "right": scan("Departments"),
    }

    result = executor.execute(plan)

    assert len(result.rows) == 5
    assert_clean(executor)


@pytest.mark.parametrize(
    "join_type",
    [
        "nested_loop_join",
        "sort_merge_join",
        "hash_join",
    ],
)
def test_join_rejects_unknown_relation(database_dir, join_type):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": join_type,
        "condition": "WrongTable.department = Departments.id",
        "left": scan("Employees"),
        "right": scan("Departments"),
    }

    with pytest.raises(ValueError, match="Unknown column"):
        executor.execute(plan)

    assert_clean(executor)


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("UnionAll", [1, 2, 2, 2, 3, 3, 3, 4, 5]),
        ("Union", [1, 2, 3, 4, 5]),
        ("Intersect", [2, 3]),
        ("Except", [1, 4]),
    ],
)
def test_set_operations(database_dir, operation, expected):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": operation,
        "left": scan("NumbersA"),
        "right": scan("NumbersB"),
    }

    result = executor.execute(plan)

    assert sorted(row[0] for row in result.rows) == expected
    assert_clean(executor)


@pytest.mark.parametrize("mode", ["sort", "hash"])
def test_distinct(database_dir, mode):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "Distinct",
        "mode": mode,
        "child": scan("NumbersA"),
    }

    result = executor.execute(plan)

    assert sorted(row[0] for row in result.rows) == [1, 2, 3, 4]
    assert_clean(executor)


def test_execute_plan_from_file(database_dir, tmp_path):
    executor = PhysicalPlanExecutor(database_dir)

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "op": "Limit",
                "count": 1,
                "child": scan("Employees"),
            }
        ),
        encoding="utf-8",
    )

    result = executor.execute_file(plan_path)

    assert result.rows == [(1, 10, "Alice", 70000)]
    assert_clean(executor)


def test_failed_filter_releases_resources(database_dir):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "Filter",
        "column": "Employees.missing",
        "comparison": "=",
        "value": 1,
        "child": scan("Employees"),
    }

    with pytest.raises(ValueError, match="Unknown column"):
        executor.execute(plan)

    assert_clean(executor)


@pytest.mark.parametrize(
    "inner_join",
    [
        "NestedLoopJoin",
        "SortMergeJoin",
        "GraceHashJoin",
    ],
)
def test_nested_join_with_four_frames(database_dir, inner_join):
    executor = PhysicalPlanExecutor(database_dir, frames=4)

    plan = {
        "op": "NestedLoopJoin",
        "left_key": "Employees.department",
        "right_key": "Departments.id",
        "left": {
            "op": inner_join,
            "left_key": "Employees.department",
            "right_key": "Departments.id",
            "left": scan("Employees"),
            "right": scan("Departments"),
        },
        "right": scan("Departments"),
    }

    # The inner join produces columns from Employees and Departments.
    # The outer join matches Employees.department to another Departments.id.
    result = executor.execute(plan)

    assert len(result.rows) == 5
    assert_clean(executor)


@pytest.mark.parametrize(
    "join_type",
    [
        "NestedLoopJoin",
        "SortMergeJoin",
        "GraceHashJoin",
    ],
)
def test_join_statistics_after_close(database_dir, join_type):
    executor = PhysicalPlanExecutor(database_dir, frames=4)

    plan = {
        "op": join_type,
        "left_key": "Employees.department",
        "right_key": "Departments.id",
        "left": scan("Employees"),
        "right": scan("Departments"),
    }

    result = executor.execute(plan)

    assert len(result.rows) == 5
    assert result.counters["tuples_out"] == 5
    assert result.counters["page_reads"] >= 0
    assert result.counters["page_writes"] >= 0

    assert_clean(executor)


def test_execution_collects_operator_statistics(database_dir):
    executor = PhysicalPlanExecutor(database_dir)

    plan = {
        "op": "Limit",
        "count": 2,
        "child": {
            "op": "Project",
            "columns": ["Employees.name"],
            "child": {
                "op": "Filter",
                "column": "Employees.salary",
                "comparison": ">",
                "value": 50000,
                "child": scan("Employees"),
            },
        },
    }

    result = executor.execute(plan)

    assert result.rows == [
        ("Alice",),
        ("Charlie",),
    ]

    assert result.operator_stats is not None

    names = [item["operator"] for item in result.operator_stats]

    assert names == [
        "Limit",
        "Project",
        "Filter",
        "SeqScan",
    ]

    assert result.operator_stats[0]["depth"] == 0
    assert result.operator_stats[3]["depth"] == 3

    assert result.buffer_stats is not None
    assert result.buffer_stats["reads"] >= 0
    assert result.buffer_stats["writes"] >= 0

    assert_clean(executor)


def test_large_nested_join_with_four_frames(tmp_path):
    """Nested joins must handle multi-page inputs using only B=4."""
    catalog = Catalog(tmp_path)

    metadata = catalog.create_table(
        "LargeR",
        "id:INT,key:INT",
    )

    heap = HeapFile(tmp_path / metadata.filename)

    for value in range(500):
        heap.insert(
            encode_record(
                (value, value % 10),
                metadata.schema,
            )
        )

    heap.flush()

    metadata = catalog.create_table(
        "LargeS",
        "key:INT",
    )

    heap = HeapFile(tmp_path / metadata.filename)

    for value in range(10):
        heap.insert(encode_record((value,), metadata.schema))

    heap.flush()

    executor = PhysicalPlanExecutor(tmp_path, frames=4)

    plan = {
        "op": "NestedLoopJoin",
        "left_key": "LargeR.key",
        "right_key": "LargeS.key",
        "left": {
            "op": "SortMergeJoin",
            "left_key": "LargeR.key",
            "right_key": "LargeS.key",
            "left": scan("LargeR"),
            "right": scan("LargeS"),
        },
        "right": scan("LargeS"),
    }

    result = executor.execute(plan)

    assert len(result.rows) == 500
    assert_clean(executor)


def test_limit_closes_nested_join_early(database_dir):
    """Stopping a join early must release every reserved frame."""
    executor = PhysicalPlanExecutor(database_dir, frames=4)

    plan = {
        "op": "Limit",
        "count": 1,
        "child": {
            "op": "NestedLoopJoin",
            "left_key": "Employees.department",
            "right_key": "Departments.id",
            "left": scan("Employees"),
            "right": scan("Departments"),
        },
    }

    result = executor.execute(plan)

    assert len(result.rows) == 1
    assert_clean(executor)


def test_failed_nested_join_releases_frames(database_dir):
    """Invalid nested join keys must not leak shared frames."""
    executor = PhysicalPlanExecutor(database_dir, frames=4)

    plan = {
        "op": "NestedLoopJoin",
        "left_key": "Employees.missing",
        "right_key": "Departments.id",
        "left": {
            "op": "SortMergeJoin",
            "left_key": "Employees.department",
            "right_key": "Departments.id",
            "left": scan("Employees"),
            "right": scan("Departments"),
        },
        "right": scan("Departments"),
    }

    with pytest.raises(
        ValueError,
        match="Unknown column",
    ):
        executor.execute(plan)

    assert_clean(executor)
