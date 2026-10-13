import pytest

from src.parser.ast import (
    AttributeReference,
    BinaryExpression,
    BinaryOperator,
    BooleanBinaryCondition,
    BooleanOperator,
    Comparison,
    ComparisonOperator,
    Distinct,
    Join,
    Not,
    NumberLiteral,
    Project,
    RelationDefinition,
    RelationReference,
    Rename,
    Select,
    Sort,
    SortDictionary,
    StringLiteral,
)
from src.parser.serialization import ast_from_json, ast_to_json


@pytest.mark.parametrize(
    "node",
    [
        RelationReference("R"),
        AttributeReference("a", "R"),
        NumberLiteral(10),
        StringLiteral("hello"),
        Comparison(
            AttributeReference("a", "R"),
            ComparisonOperator.EQUAL,
            NumberLiteral(10),
        ),
        Not(
            Comparison(
                AttributeReference("a"),
                ComparisonOperator.GREATER_THAN,
                NumberLiteral(5),
            )
        ),
        BooleanBinaryCondition(
            Comparison(
                AttributeReference("a"),
                ComparisonOperator.EQUAL,
                NumberLiteral(1),
            ),
            BooleanOperator.AND,
            Comparison(
                AttributeReference("b"),
                ComparisonOperator.EQUAL,
                NumberLiteral(2),
            ),
        ),
        Select(
            Comparison(
                AttributeReference("a"),
                ComparisonOperator.EQUAL,
                NumberLiteral(10),
            ),
            RelationReference("R"),
        ),
        Project(
            [AttributeReference("a"), AttributeReference("b")],
            RelationReference("R"),
        ),
        Rename(
            "S",
            RelationReference("R"),
            {"a": "x"},
        ),
        BinaryExpression(
            RelationReference("R"),
            BinaryOperator.UNION,
            RelationReference("S"),
        ),
        Join(
            RelationReference("R"),
            Comparison(
                AttributeReference("a", "R"),
                ComparisonOperator.EQUAL,
                AttributeReference("a", "S"),
            ),
            RelationReference("S"),
        ),
        RelationDefinition(
            "R",
            ["a", "b"],
            [[1, "hello"], [2, "world"]],
        ),
        Sort(
            AttributeReference("a"),
            SortDictionary.DESC,
            RelationReference("R"),
        ),
    ],
)
def test_ast_json_round_trip(node):
    restored = ast_from_json(ast_to_json(node))

    assert restored == node
    assert type(restored) is type(node)


def test_invalid_ast_type():
    with pytest.raises(ValueError, match="Unknown AST node type"):
        ast_from_json('{"__type__": "UnknownNode"}')


def test_invalid_root_type():
    with pytest.raises(TypeError, match="JSON does not contain an AST node"):
        ast_from_json('{"value": 10}')


def test_distinct_json_round_trip():
    expression = Distinct(
        expression=Project(
            attributes=[AttributeReference(name="Name")],
            expression=RelationReference(name="Employees"),
        )
    )

    serialized = ast_to_json(expression)
    restored = ast_from_json(serialized)

    assert restored == expression
    assert isinstance(restored, Distinct)