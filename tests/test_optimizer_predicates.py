"""Tests for parsing and estimating compiler-generated SQL predicates."""

import pytest

from src.optimizer.predicates import (
    BooleanPredicate,
    ColumnRef,
    ComparisonPredicate,
    LiteralValue,
    NotPredicate,
    estimate_condition,
    parse_predicate,
)
from src.optimizer.statistics import ColumnStatistics


@pytest.fixture
def columns():
    return {
        "Emp.age": ColumnStatistics(5, 20, 60),
        "Emp.id": ColumnStatistics(50, 1, 50),
        "Dept.id": ColumnStatistics(10, 1, 10),
        "Emp.name": ColumnStatistics(4, "Amy", "Zoe"),
    }


def test_parse_simple_comparison():
    assert parse_predicate("Emp.age >= 30") == ComparisonPredicate(
        ColumnRef("Emp.age"), ">=", LiteralValue(30)
    )


def test_parse_equality():
    assert parse_predicate("Emp.age = 30") == ComparisonPredicate(
        ColumnRef("Emp.age"), "=", LiteralValue(30)
    )


def test_parse_negative_integer():
    assert parse_predicate("Emp.age > -5") == ComparisonPredicate(
        ColumnRef("Emp.age"), ">", LiteralValue(-5)
    )


def test_parse_string_literal():
    assert parse_predicate("Emp.name = 'Amy'") == ComparisonPredicate(
        ColumnRef("Emp.name"), "=", LiteralValue("Amy")
    )


def test_parse_escaped_string():
    assert parse_predicate("Emp.name = 'O''Brien'") == ComparisonPredicate(
        ColumnRef("Emp.name"), "=", LiteralValue("O'Brien")
    )


def test_parse_parenthesized_and():
    result = parse_predicate("(Emp.age >= 30 AND Emp.age < 50)")
    assert isinstance(result, BooleanPredicate)
    assert result.operator == "AND"


def test_parse_nested_or():
    result = parse_predicate("((Emp.age = 20 OR Emp.age = 30) AND Emp.id > 5)")
    assert isinstance(result, BooleanPredicate)
    assert result.operator == "AND"
    assert isinstance(result.left, BooleanPredicate)


def test_parse_not():
    result = parse_predicate("NOT (Emp.age = 20)")
    assert isinstance(result, NotPredicate)


def test_boolean_precedence():
    result = parse_predicate("Emp.age = 20 OR Emp.age = 30 AND Emp.id = 1")
    assert isinstance(result, BooleanPredicate)
    assert result.operator == "OR"
    assert isinstance(result.right, BooleanPredicate)
    assert result.right.operator == "AND"


def test_parse_join():
    result = parse_predicate("Emp.id = Dept.id")
    assert result == ComparisonPredicate(ColumnRef("Emp.id"), "=", ColumnRef("Dept.id"))


def test_equality_selectivity(columns):
    assert estimate_condition("Emp.age = 30", columns) == pytest.approx(0.2)


def test_range_selectivity(columns):
    assert estimate_condition("Emp.age < 40", columns) == pytest.approx(0.5)


def test_and_selectivity(columns):
    assert estimate_condition(
        "(Emp.age = 30 AND Emp.id = 10)", columns
    ) == pytest.approx(0.2 * 0.02)


def test_or_selectivity(columns):
    assert estimate_condition(
        "(Emp.age = 30 OR Emp.id = 10)", columns
    ) == pytest.approx(0.2 + 0.02 - 0.2 * 0.02)


def test_not_selectivity(columns):
    assert estimate_condition("NOT (Emp.age = 30)", columns) == pytest.approx(0.8)


def test_join_selectivity(columns):
    assert estimate_condition("Emp.id = Dept.id", columns) == pytest.approx(1 / 50)


def test_join_disjoint_ranges(columns):
    assert estimate_condition("Emp.age = Dept.id", columns) == 0


def test_reversed_comparison(columns):
    assert estimate_condition("30 < Emp.age", columns) == pytest.approx(0.75)


def test_unqualified_column(columns):
    assert estimate_condition("age = 30", columns) == pytest.approx(0.2)


def test_missing_column_statistics(columns):
    assert estimate_condition("Emp.salary = 1000", columns) == pytest.approx(0.1)


def test_literal_comparison():
    assert estimate_condition("1 = 1", {}) == 1
    assert estimate_condition("1 = 2", {}) == 0


def test_same_column_comparison(columns):
    assert estimate_condition("Emp.id = Emp.id", columns) == 1


def test_invalid_empty_predicate():
    with pytest.raises(ValueError):
        parse_predicate("")


def test_invalid_operator():
    with pytest.raises(ValueError):
        parse_predicate("Emp.age LIKE 30")


def test_unbalanced_parentheses():
    with pytest.raises(ValueError):
        parse_predicate("(Emp.age = 30")


def test_invalid_token():
    with pytest.raises(ValueError):
        parse_predicate("Emp.age = @30")


def test_trailing_tokens():
    with pytest.raises(ValueError):
        parse_predicate("Emp.age = 30 extra")
