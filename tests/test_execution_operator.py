import pytest

from src.execution.operator import Operator, OperatorCounters


def test_default_counters():
    counters = OperatorCounters()

    assert counters.tuples_out == 0
    assert counters.comparisons == 0
    assert counters.page_reads == 0
    assert counters.page_writes == 0


def test_operator_is_abstract():
    with pytest.raises(TypeError):
        type.__call__(Operator)


def test_concrete_operator():
    class DummyOperator(Operator):
        def open(self):
            pass

        def next(self):
            return None

        def close(self):
            pass

    operator = DummyOperator()

    assert operator.schema == []
    assert operator.next() is None

    assert operator.counters() == {
        "tuples_out": 0,
        "comparisons": 0,
        "page_reads": 0,
        "page_writes": 0,
    }


def test_counters_are_independent():
    class DummyOperator(Operator):
        def open(self):
            pass

        def next(self):
            return None

        def close(self):
            pass

    first = DummyOperator()
    second = DummyOperator()

    first._counters.tuples_out = 5

    assert first.counters()["tuples_out"] == 5
    assert second.counters()["tuples_out"] == 0
