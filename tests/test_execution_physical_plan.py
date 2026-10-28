"""Tests for JSON physical-plan construction and execution."""

import json

import pytest

from src.execution.filter import Filter
from src.execution.grace_hash_join import GraceHashJoin
from src.execution.intersect import Intersect
from src.execution.limit import Limit
from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.physical_plan import PhysicalPlanBuilder
from src.execution.plan_executor import PhysicalPlanExecutor
from src.execution.project import Project
from src.execution.seq_scan import SeqScan


def test_build_nested_plan(tmp_path):
    pages = SharedPageManager(4)
    builder = PhysicalPlanBuilder(tmp_path, pages)

    plan = {
        "op": "Limit",
        "count": 5,
        "child": {
            "op": "Project",
            "columns": ["employees.id"],
            "child": {
                "op": "Filter",
                "column": "employees.id",
                "comparison": ">",
                "value": 10,
                "child": {
                    "op": "SeqScan",
                    "table": "employees",
                },
            },
        },
    }

    root = builder.build(plan)

    assert isinstance(root, Limit)
    assert root.count == 5

    project = root.child
    assert isinstance(project, Project)
    assert project.columns == ["employees.id"]

    filter_op = project.child
    assert isinstance(filter_op, Filter)
    assert filter_op.column == "employees.id"

    scan = filter_op.child
    assert isinstance(scan, SeqScan)
    assert scan.table_name == "employees"


def test_build_join_plan(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))

    plan = {
        "op": "GraceHashJoin",
        "left_key": "employees.id",
        "right_key": "departments.id",
        "left": {
            "op": "SeqScan",
            "table": "employees",
        },
        "right": {
            "op": "SeqScan",
            "table": "departments",
        },
    }

    root = builder.build(plan)

    assert isinstance(root, GraceHashJoin)
    assert root.left_key == "employees.id"
    assert root.right_key == "departments.id"

    assert isinstance(root.left, SeqScan)
    assert isinstance(root.right, SeqScan)
    assert root.left.pages is root.pages
    assert root.right.pages is root.pages


def test_build_set_operation(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))

    plan = {
        "op": "Intersect",
        "left": {"op": "SeqScan", "table": "a"},
        "right": {"op": "SeqScan", "table": "b"},
    }

    root = builder.build(plan)

    assert isinstance(root, Intersect)
    assert root.operation == "intersect"


def test_json_plan_round_trip(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))
    plan = {
        "op": "Limit",
        "count": 3,
        "child": {"op": "SeqScan", "table": "items"},
    }

    root = builder.from_json(json.dumps(plan))

    assert isinstance(root, Limit)
    assert root.count == 3


def test_missing_field(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))

    with pytest.raises(ValueError, match="Missing plan field"):
        builder.build({"op": "Filter"})


def test_unknown_operator(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))

    with pytest.raises(ValueError, match="Unsupported"):
        builder.build({"op": "UnknownOperator"})


def test_invalid_node(tmp_path):
    builder = PhysicalPlanBuilder(tmp_path, SharedPageManager(4))

    with pytest.raises(TypeError, match="must be an object"):
        builder.build(["SeqScan"])  # pyright: ignore[reportArgumentType]


def test_execute_empty_plan(tmp_path):
    executor = PhysicalPlanExecutor(tmp_path)

    with pytest.raises(ValueError, match="Invalid page ID"):
        executor.execute(
            {
                "op": "SeqScan",
                "table": "missing",
            }
        )

    assert not executor.pages.reserved_frames
    assert all(count == 0 for count in executor.pages.pin_counts)


def test_execute_operator_cleanup(tmp_path):
    executor = PhysicalPlanExecutor(tmp_path)

    class FailingOperator(Operator):
        def __init__(self):
            self.schema = [("x", "INT")]
            self.closed = False

        def open(self):
            pass

        def next(self):
            raise RuntimeError("Intentional failure")

        def close(self):
            self.closed = True

        def counters(self):
            return {}

    root = FailingOperator()

    with pytest.raises(RuntimeError, match="Intentional"):
        executor.execute_operator(root)

    assert root.closed


@pytest.mark.parametrize(
    ("official_name", "legacy_name"),
    [
        ("seqscan", "SeqScan"),
        ("filter", "Filter"),
        ("project", "Project"),
        ("limit", "Limit"),
        ("sort", "Sort"),
        ("distinct", "Distinct"),
        ("group_by", "GroupBy"),
        ("nested_loop_join", "NestedLoopJoin"),
        ("sort_merge_join", "SortMergeJoin"),
        ("hash_join", "GraceHashJoin"),
        ("union_all", "UnionAll"),
        ("union", "Union"),
        ("intersect", "Intersect"),
        ("except", "Except"),
    ],
)
def test_official_operator_names_are_supported(official_name, legacy_name):
    assert PhysicalPlanBuilder.OPERATOR_NAMES[official_name] == legacy_name


def test_join_condition_preserves_column_names():
    left, right = PhysicalPlanBuilder._parse_join_condition("R.b = S.b")

    assert left == "R.b"
    assert right == "S.b"


def test_join_condition_rejects_non_equality():
    with pytest.raises(ValueError, match="equality"):
        PhysicalPlanBuilder._parse_join_condition("R.b > S.b")


def test_join_condition_rejects_literal_operand():
    with pytest.raises(TypeError, match="column"):
        PhysicalPlanBuilder._parse_join_condition("R.b = 5")


def test_filter_condition_parses_integer():
    column, comparison, value = PhysicalPlanBuilder._parse_filter_condition(
        "R.age >= 18"
    )

    assert column == "R.age"
    assert comparison == ">="
    assert value == 18


def test_filter_condition_rejects_compound_expression():
    with pytest.raises(TypeError, match="single comparison"):
        PhysicalPlanBuilder._parse_filter_condition("age > 18 and score > 50")
