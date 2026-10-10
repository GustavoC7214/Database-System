import pytest

from src.engine.relation import Attribute, Relation, Row


def test_identical_rows_are_equal():
    row1 = Row(["E1", "John", 32])
    row2 = Row(["E1", "John", 32])

    assert row1 == row2

def test_rows_with_different_values_are_not_equal():
    row1 = Row(["E1", "John", 32])
    row2 = Row(["E1", "John", 28])

    assert row1 != row2

def test_rows_with_different_value_types_are_not_equal():
    row1 = Row(["1"])
    row2 = Row([1])

    assert row1 != row2

def test_rows_with_different_lengths_are_not_equal():
    row1 = Row(["E1", "John", 32])
    row2 = Row(["E1", "John"])

    assert row1 != row2

def test_relation_rejects_row_with_wrong_number_of_values():
    attributes = [
    Attribute("Employees", "E1"),
    Attribute("Employees", "John"),
    Attribute("Employees", "20"),
    ]
    row = Row(["E1", "John"])

    with pytest.raises(ValueError):
        Relation("Employees", attributes, [row])


def test_relations_removed_duplicate_rows():
    attributes = [
    Attribute("Employees", "E1"),
    Attribute("Employees", "Alice"),
    Attribute("Employees", "18")
    ]
    row1 = Row(["E1", "John", 32])
    row2 = Row(["E1", "John", 32])
    row3 = Row(["E2", "Alice", 20])

    relation = Relation("Employees", attributes, [row1, row2, row3])

    assert len(relation.rows) == 2
