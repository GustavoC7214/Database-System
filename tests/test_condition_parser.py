import pytest

from src.parser.ast import (
    AttributeReference,
    BooleanBinaryCondition,
    BooleanOperator,
    Comparison,
    Not,
)
from src.parser.parser import ParseError, parse_condition_text


def test_qualified_attributes():
    condition = parse_condition_text("R.b = S.b")

    assert isinstance(condition, Comparison)
    assert condition.left == AttributeReference(name="b", relation="R")
    assert condition.right == AttributeReference(name="b", relation="S")


def test_and_or_precedence():
    condition = parse_condition_text("a = 1 OR b = 2 AND c = 3")

    assert isinstance(condition, BooleanBinaryCondition)
    assert condition.operator == BooleanOperator.OR

    assert isinstance(condition.right, BooleanBinaryCondition)
    assert condition.right.operator == BooleanOperator.AND


def test_not_condition():
    condition = parse_condition_text("NOT a = 1")

    assert isinstance(condition, Not)
    assert isinstance(condition.condition, Comparison)


def test_parentheses_override_precedence():
    condition = parse_condition_text("(a = 1 OR b = 2) AND c = 3")

    assert isinstance(condition, BooleanBinaryCondition)
    assert condition.operator == BooleanOperator.AND

    assert isinstance(condition.left, BooleanBinaryCondition)
    assert condition.left.operator == BooleanOperator.OR


def test_rejects_trailing_tokens():
    with pytest.raises(ParseError):
        parse_condition_text("a = 1 b = 2")


def test_rejects_incomplete_condition():
    with pytest.raises(ParseError):
        parse_condition_text("a =")
