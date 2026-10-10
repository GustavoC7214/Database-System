import pytest

from src.lexer.tokenizer import Tokenizer
from src.parser.ast import (
    AttributeReference,
    BinaryExpression,
    BinaryOperator,
    BooleanBinaryCondition,
    BooleanOperator,
    Comparison,
    ComparisonOperator,
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
from src.parser.parser import ParseError, Parser


def test_relation_reference():
    tokens = Tokenizer("R").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == RelationReference(name="R")

def test_parenthesized_relation_reference():
    tokens = Tokenizer("(R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == RelationReference(name="R")

def test_union_expression():
    tokens = Tokenizer("R union S").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == BinaryExpression(
        left=RelationReference(name="R"),
        operator=BinaryOperator.UNION,
        right=RelationReference(name="S")
    )

def test_set_operators_are_left_associative():
    tokens = Tokenizer("R union S minus T").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == BinaryExpression(
        left=BinaryExpression(
            left=RelationReference(name="R"),
            operator=BinaryOperator.UNION,
            right=RelationReference(name="S")
        ),
        operator=BinaryOperator.MINUS,
        right=RelationReference(name="T")
    )

def test_times_has_higher_precedence_than_union():
    tokens = Tokenizer("R union S times T").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == BinaryExpression(
        left=RelationReference(name="R"),
        operator=BinaryOperator.UNION,
        right=BinaryExpression(
            left=RelationReference(name="S"),
            operator=BinaryOperator.TIMES,
            right=RelationReference(name="T")
        )
    )

def test_select_expression():
    tokens = Tokenizer("select[Age>=30](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
            right=NumberLiteral(value=30)
        ),
        expression=RelationReference(name="R")
    )

def test_boolean_operator_precedence():
    tokens = Tokenizer(
        "select[Age>=30 or Name='Bob' and Age<50](R)"
    ).tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=BooleanBinaryCondition(
            left=Comparison(
                left=AttributeReference(name="Age"),
                operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                right=NumberLiteral(value=30)
            ),
            operator=BooleanOperator.OR,
            right=BooleanBinaryCondition(
                left=Comparison(
                    left=AttributeReference(name="Name"),
                    operator=ComparisonOperator.EQUAL,
                    right=StringLiteral(value="Bob")
                ),
                operator=BooleanOperator.AND,
                right=Comparison(
                    left=AttributeReference(name="Age"),
                    operator=ComparisonOperator.LESS_THAN,
                    right=NumberLiteral(value=50)
                )
            )
        ),
        expression=RelationReference(name="R")
    )

def test_not_condition():
    tokens = Tokenizer("select[not Age>=30](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=Not(
            condition=Comparison(
                left=AttributeReference(name="Age"),
                operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                right=NumberLiteral(value=30)
            )
        ),
        expression=RelationReference(name="R")
    )

def test_not_keyword_as_attribute():
    tokens = Tokenizer("select[not=30](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=Comparison(
            left=AttributeReference(name="not"),
            operator=ComparisonOperator.EQUAL,
            right=NumberLiteral(value=30)
        ),
        expression=RelationReference(name="R")
    )

def test_project_expression():
    tokens = Tokenizer("project[Name, Age](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Project(
        attributes=[
            AttributeReference(name="Name"),
            AttributeReference(name="Age")
        ],
        expression=RelationReference(name="R")
    )

def test_project_with_qualified_attributes():
    tokens = Tokenizer(
        "project[Member.Name, Member.Age](Member)"
    ).tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Project(
        attributes=[
            AttributeReference(name="Name", relation="Member"),
            AttributeReference(name="Age", relation="Member")
        ],
        expression=RelationReference(name="Member")
    )

def test_rename_expression():
    tokens = Tokenizer("rename[M](Member)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Rename(
        new_name="M",
        expression=RelationReference(name="Member")
    )

def test_sort_ascending():
    tokens = Tokenizer("sort[Age asc](Member)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Sort(
        attribute=AttributeReference(name="Age"),
        direction=SortDictionary.ASC,
        expression=RelationReference(name="Member")
    )


def test_sort_descending():
    tokens = Tokenizer("sort[Age desc](Member)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Sort(
        attribute=AttributeReference(name="Age"),
        direction=SortDictionary.DESC,
        expression=RelationReference(name="Member")
    )


def test_sort_with_qualified_attribute():
    tokens = Tokenizer("sort[Member.Age desc](Member)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Sort(
        attribute=AttributeReference(
            name="Age",
            relation="Member"
        ),
        direction=SortDictionary.DESC,
        expression=RelationReference(name="Member")
    )


def test_sort_nested_expression():
    tokens = Tokenizer(
        "sort[Age desc](select[Age>25](Member))"
    ).tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Sort(
        attribute=AttributeReference(name="Age"),
        direction=SortDictionary.DESC,
        expression=Select(
            condition=Comparison(
                left=AttributeReference(name="Age"),
                operator=ComparisonOperator.GREATER_THAN,
                right=NumberLiteral(value=25)
            ),
            expression=RelationReference(name="Member")
        )
    )


def test_sort_rejects_invalid_direction():
    tokens = Tokenizer("sort[Age sideways](Member)").tokenize()

    with pytest.raises(ParseError) as exc_info:
        Parser(tokens).parse()

    message = str(exc_info.value)

    assert "asc" in message
    assert "desc" in message
    assert "sideways" in message

def test_join_expression():
    tokens = Tokenizer(
        "Member join[Member.Place=Chapter.Location] Chapter"
    ).tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Join(
        left=RelationReference(name="Member"),
        condition=Comparison(
            left=AttributeReference(name="Place", relation="Member"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="Location", relation="Chapter")
        ),
        right=RelationReference(name="Chapter")
    )

def test_join_has_higher_precedence_than_union():
    tokens = Tokenizer(
        "R union S join[S.Id=T.Id] T"
    ).tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == BinaryExpression(
        left=RelationReference(name="R"),
        operator=BinaryOperator.UNION,
        right=Join(
            left=RelationReference(name="S"),
            condition=Comparison(
                left=AttributeReference(name="Id", relation="S"),
                operator=ComparisonOperator.EQUAL,
                right=AttributeReference(name="Id", relation="T")
            ),
            right=RelationReference(name="T")
        )
    )

def test_multiple_not_conditions():
    tokens = Tokenizer("select[not not Age=30](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=Not(
            condition=Not(
                condition=Comparison(
                    left=AttributeReference(name="Age"),
                    operator=ComparisonOperator.EQUAL,
                    right=NumberLiteral(value=30)
                )
            )
        ),
        expression=RelationReference(name="R")
    )

def test_union_keyword_as_attribute():
    tokens = Tokenizer("select[union=3](R)").tokenize()
    parser = Parser(tokens)
    result = parser.parse()

    assert result == Select(
        condition=Comparison(
            left=AttributeReference(name="union"),
            operator=ComparisonOperator.EQUAL,
            right=NumberLiteral(value=3)
        ),
        expression=RelationReference(name="R")
    )

def test_relation_definition():
    source = """Member(Id, Name, Age) = {
1, Alice, 22
2, 'Bob Smith', 25
}"""

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, RelationDefinition)
    assert result.name == "Member"
    assert result.attributes == ["Id", "Name", "Age"]
    assert result.rows == [
        [1, "Alice", 22],
        [2, "Bob Smith", 25]
    ]

def test_empty_relation_definition():
    source = """Empty(Id, Name) = {
}"""

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, RelationDefinition)
    assert result.name == "Empty"
    assert result.attributes == ["Id", "Name"]
    assert result.rows == []

def test_relation_definition_requires_equals():
    source = """Member(Id, Name) > {
1, Alice
}"""

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError):
        Parser(tokens).parse()

def test_relation_definition_allows_arity_mismatch_during_parsing():
    source = """Member(Id, Name, Age) = {
1, Alice
}"""

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, RelationDefinition)
    assert result.attributes == ["Id", "Name", "Age"]
    assert result.rows == [[1, "Alice"]]

def test_parser_rejects_trailing_tokens():
    source = "R S"

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError):
        Parser(tokens).parse()

def test_comparison_operators_are_non_associative():
    source = "select[Age = 30 = 40](Member)"

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError):
        Parser(tokens).parse()

def test_parentheses_override_relational_precedence():
    source = "(R union S) times T"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, BinaryExpression)
    assert result.operator == BinaryOperator.TIMES

    assert isinstance(result.left, BinaryExpression)
    assert result.left.operator == BinaryOperator.UNION

def test_required_case_10_union_minus_grouping():
    source = "A union B minus C"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, BinaryExpression)
    assert result.operator == BinaryOperator.MINUS

    assert isinstance(result.left, BinaryExpression)
    assert result.left.operator == BinaryOperator.UNION

def test_missing_closing_parenthesis():
    source = "select[Age>30](R"

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError) as exc_info:
        Parser(tokens).parse()

    message = str(exc_info.value)

    assert "Expected ')'" in message
    assert "line" in message
    assert "column" in message

def test_empty_projection_attribute_list():
    source = "project[](R)"

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError):
        Parser(tokens).parse()

def test_required_case_12_not_and_or_precedence():
    source = "select[not (a=1 and b=2) or c>3](R)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, Select)

    assert isinstance(result.condition, BooleanBinaryCondition)
    assert result.condition.operator == BooleanOperator.OR

    assert isinstance(result.condition.left, Not)
    assert isinstance(result.condition.left.condition, BooleanBinaryCondition)
    assert result.condition.left.condition.operator == BooleanOperator.AND

    assert isinstance(result.condition.right, Comparison)
    assert result.condition.right.operator == ComparisonOperator.GREATER_THAN

def test_required_case_14_nested_operations():
    source = "project[Name](select[Age>30](select[DID='D1'](Employees)))"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, Project)

    assert isinstance(result.expression, Select)

    assert isinstance(result.expression.expression, Select)

    assert isinstance(
        result.expression.expression.expression,
        RelationReference
    )
    assert result.expression.expression.expression.name == "Employees"

def test_required_case_15_parentheses_override_precedence():
    source = "(A union B) minus (C intersect D)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, BinaryExpression)
    assert result.operator == BinaryOperator.MINUS

    assert isinstance(result.left, BinaryExpression)
    assert result.left.operator == BinaryOperator.UNION

    assert isinstance(result.right, BinaryExpression)
    assert result.right.operator == BinaryOperator.INTERSECT


def test_required_case_13_parenthesized_boolean_condition():
    source = "select[(a=1 and b=2) or c=3](R)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    assert isinstance(result, Select)
    assert isinstance(result.condition, BooleanBinaryCondition)
    assert result.condition.operator == BooleanOperator.OR

    left = result.condition.left
    right = result.condition.right

    assert isinstance(left, BooleanBinaryCondition)
    assert left.operator == BooleanOperator.AND

    assert isinstance(left.left, Comparison)
    assert isinstance(left.left.left, AttributeReference)
    assert left.left.left.name == "a"
    assert left.left.operator == ComparisonOperator.EQUAL
    assert isinstance(left.left.right, NumberLiteral)
    assert left.left.right.value == 1

    assert isinstance(left.right, Comparison)
    assert isinstance(left.right.left, AttributeReference)
    assert left.right.left.name == "b"
    assert left.right.operator == ComparisonOperator.EQUAL
    assert isinstance(left.right.right, NumberLiteral)
    assert left.right.right.value == 2

    assert isinstance(right, Comparison)
    assert isinstance(right.left, AttributeReference)
    assert right.left.name == "c"
    assert right.operator == ComparisonOperator.EQUAL
    assert isinstance(right.right, NumberLiteral)
    assert right.right.value == 3


def test_required_case_2_whitespace_does_not_change_parse_tree():
    compact = "select[x1=3](R)"
    spaced = "select [ x1 = 3 ] ( R )"

    compact_ast = Parser(Tokenizer(compact).tokenize()).parse()
    spaced_ast = Parser(Tokenizer(spaced).tokenize()).parse()

    assert compact_ast == spaced_ast


def test_empty_projection_reports_clear_syntax_error():
    source = "project[](R)"

    tokens = Tokenizer(source).tokenize()

    with pytest.raises(ParseError) as exc_info:
        Parser(tokens).parse()

    message = str(exc_info.value)

    assert "Expected identifier" in message
    assert "found ']'" in message
    assert "line 1" in message
    assert "column 9" in message