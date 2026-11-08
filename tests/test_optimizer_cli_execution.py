"""End-to-end tests of CLI-exported physical plans."""

import json
from collections import Counter

import pytest

from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.cli import main
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

FRAMES = 32

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
    """Create real disk-backed tables and persisted optimizer statistics."""
    catalog = Catalog(tmp_path)
    store = StatisticsStore(tmp_path)

    for name, (schema, rows) in DATA.items():
        metadata = catalog.create_table(name, schema)
        heap = HeapFile(tmp_path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()

        store.save(
            TableStatistics(
                table=name,
                n_tuples=len(rows),
                n_pages=1,
                width=32.0,
            )
        )

    return tmp_path


def export_plans(database, capsys, sql, *options):
    """Generate physical JSON through the actual optimizer CLI."""
    exit_code = main(
        [
            "plan",
            "--db",
            str(database),
            "--sql",
            sql,
            "--physical",
            "--frames",
            str(FRAMES),
            *options,
        ]
    )

    assert exit_code == 0

    output = capsys.readouterr().out
    plans = json.loads(output)

    assert isinstance(plans, list)
    assert plans

    return plans


def execute_export(database, plan):
    """Execute a JSON-round-tripped plan and verify buffer cleanup."""
    executor = PhysicalPlanExecutor(database, frames=FRAMES)

    result = executor.execute_json(json.dumps(plan))

    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)

    return result


def assert_equivalent(left, right):
    assert left.schema == right.schema
    assert Counter(map(tuple, left.rows)) == Counter(map(tuple, right.rows))


def test_cli_scan_executes_real_rows(database, capsys):
    plans = export_plans(
        database,
        capsys,
        "SELECT * FROM Emp;",
    )

    result = execute_export(database, plans[0])

    assert len(result.rows) == 6
    assert result.schema[0] == ("Emp.eid", "INT")
    assert (1, "Alice", 35, 10) in result.rows


def test_cli_projection_executes(database, capsys):
    plans = export_plans(
        database,
        capsys,
        "SELECT name FROM Emp;",
    )

    result = execute_export(database, plans[0])

    assert result.schema == [("Emp.name", "VARCHAR(40)")]
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


def test_cli_filter_executes(database, capsys):
    plans = export_plans(
        database,
        capsys,
        "SELECT name FROM Emp WHERE age > 30;",
    )

    result = execute_export(database, plans[0])

    assert Counter(result.rows) == Counter(
        [
            ("Alice",),
            ("Charlie",),
            ("Alice",),
        ]
    )


def test_cli_join_executes(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    plans = export_plans(
        database,
        capsys,
        sql,
        "--no-join-order",
    )

    result = execute_export(database, plans[0])

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


def test_cli_two_table_join_order_equivalence(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    original = export_plans(
        database,
        capsys,
        sql,
        "--no-join-order",
    )[0]

    optimized = export_plans(
        database,
        capsys,
        sql,
    )[0]

    original_result = execute_export(database, original)
    optimized_result = execute_export(database, optimized)

    assert_equivalent(original_result, optimized_result)


def test_cli_three_table_join_order_equivalence(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title, Office.city
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did
    JOIN Office ON Dept.did = Office.did;
    """

    original = export_plans(
        database,
        capsys,
        sql,
        "--no-join-order",
    )[0]

    optimized = export_plans(
        database,
        capsys,
        sql,
    )[0]

    original_result = execute_export(database, original)
    optimized_result = execute_export(database, optimized)

    assert_equivalent(original_result, optimized_result)
    assert len(optimized_result.rows) == 9


def test_cli_multiple_queries_execute(database, capsys):
    sql = """
    SELECT name FROM Emp;
    SELECT title FROM Dept;
    """

    plans = export_plans(database, capsys, sql)

    assert len(plans) == 2

    first = execute_export(database, plans[0])
    second = execute_export(database, plans[1])

    assert len(first.rows) == 6
    assert len(second.rows) == 3


def test_cli_execution_counters_available(database, capsys):
    plans = export_plans(
        database,
        capsys,
        "SELECT name FROM Emp WHERE age > 30;",
    )

    result = execute_export(database, plans[0])

    assert result.counters["tuples_out"] == 3
    assert result.counters["page_reads"] >= 0
    assert result.counters["page_writes"] >= 0
    assert result.operator_stats is not None
    assert result.buffer_stats is not None


def test_cli_rejects_unsupported_physical_query(database, capsys):
    sql = """
    SELECT name
    FROM Emp
    WHERE age > 30 OR did = 10;
    """

    with pytest.raises(SystemExit) as exc:
        export_plans(database, capsys, sql)

    assert exc.value.code == 2
    assert "Only AND compound filters are supported" in capsys.readouterr().err


def test_cli_export_is_deterministic(database, capsys):
    sql = """
    SELECT Emp.name, Dept.title
    FROM Emp
    JOIN Dept ON Emp.did = Dept.did;
    """

    first = export_plans(database, capsys, sql)
    second = export_plans(database, capsys, sql)

    assert first == second
