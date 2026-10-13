import pytest

from src.engine.evaluator import evaluate_condition_on_row
from src.engine.relation import Attribute, Relation, Row
from src.parser.parser import parse_condition_text


@pytest.fixture
def relation():
    return Relation(
        name="R",
        attributes=[
            Attribute("R", "a"),
            Attribute("R", "b"),
            Attribute("S", "b"),
        ],
        rows=[
            Row([10, 20, 20]),
        ],
    )


def test_simple_comparison(relation):
    condition = parse_condition_text("R.a = 10")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is True


def test_false_comparison(relation):
    condition = parse_condition_text("R.a > 15")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is False


def test_qualified_attribute_comparison(relation):
    condition = parse_condition_text("R.b = S.b")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is True


def test_and_condition(relation):
    condition = parse_condition_text("R.a = 10 AND R.b = 20")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is True


def test_or_condition(relation):
    condition = parse_condition_text("R.a = 5 OR R.b = 20")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is True


def test_not_condition(relation):
    condition = parse_condition_text("NOT R.a = 5")
    row = relation.rows[0]

    assert evaluate_condition_on_row(condition, relation, row) is True


def test_ambiguous_attribute(relation):
    condition = parse_condition_text("b = 20")
    row = relation.rows[0]

    with pytest.raises(NameError, match="Ambiguous attribute"):
        evaluate_condition_on_row(condition, relation, row)