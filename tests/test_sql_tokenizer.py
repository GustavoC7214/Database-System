"""Tests for the Module 3 SQL tokenizer."""

import pytest

from src.sql.tokenizer import SQLLexicalError, tokenize
from src.sql.tokens import TokenType


def test_keyword_case_insensitive():
    tokens = tokenize("SeLeCt name FrOm Emp;")

    assert tokens[0].type == TokenType.KEYWORD
    assert tokens[0].value == "SELECT"
    assert tokens[2].value == "FROM"


def test_identifier_case_preserved():
    tokens = tokenize("SELECT Name FROM Emp;")

    assert tokens[1].value == "Name"
    assert tokens[3].value == "Emp"


def test_signed_integer():
    tokens = tokenize("SELECT * FROM Emp WHERE age >= -30;")

    integers = [t for t in tokens if t.type == TokenType.INTEGER]

    assert len(integers) == 1
    assert integers[0].value == "-30"


def test_escaped_string():
    tokens = tokenize("SELECT * FROM Emp WHERE name = 'O''Brien';")

    strings = [t for t in tokens if t.type == TokenType.STRING]

    assert len(strings) == 1
    assert strings[0].value == "O'Brien"


def test_comments():
    tokens = tokenize("-- comment\nSELECT name FROM Emp; -- trailing comment")

    assert tokens[0].value == "SELECT"
    assert tokens[0].line == 2
    assert tokens[-1].type == TokenType.EOF


def test_maximal_munch_operators():
    tokens = tokenize("a <= 3 AND b >= 2 AND c <> 1")

    operators = [token.value for token in tokens if token.type == TokenType.OPERATOR]

    assert operators == ["<=", ">=", "<>"]


def test_multiple_statements():
    tokens = tokenize("SELECT * FROM Emp; SELECT * FROM Dept;")

    assert sum(t.type == TokenType.SEMICOLON for t in tokens) == 2
    assert tokens[-1].type == TokenType.EOF


def test_qualified_column():
    tokens = tokenize("SELECT e.name FROM Emp AS e;")

    assert tokens[1].value == "e"
    assert tokens[2].type == TokenType.DOT
    assert tokens[3].value == "name"


def test_unterminated_string():
    with pytest.raises(SQLLexicalError, match="unterminated string literal"):
        tokenize("SELECT 'hello")


def test_invalid_character():
    with pytest.raises(SQLLexicalError, match="unexpected character"):
        tokenize("SELECT @ FROM Emp")


def test_line_and_column():
    tokens = tokenize("SELECT\n  name\nFROM Emp;")

    assert tokens[1].line == 2
    assert tokens[1].column == 3
    assert tokens[2].line == 3
    assert tokens[2].column == 1


def test_create_table():
    tokens = tokenize("CREATE TABLE Emp (id INT, name VARCHAR(30));")

    assert tokens[0].value == "CREATE"
    assert tokens[1].value == "TABLE"
    assert any(t.value == "VARCHAR" for t in tokens)


def test_insert():
    tokens = tokenize("INSERT INTO Emp VALUES (1, 'Alice');")

    assert tokens[0].value == "INSERT"
    assert tokens[1].value == "INTO"
    assert tokens[3].value == "VALUES"


def test_empty_input():
    tokens = tokenize("")

    assert len(tokens) == 1
    assert tokens[0].type == TokenType.EOF


def test_integer_at_end_of_input():
    tokens = tokenize("123")

    assert tokens[0].type == TokenType.INTEGER
    assert tokens[0].value == "123"
    assert tokens[1].type == TokenType.EOF


@pytest.mark.parametrize("value", ["0", "42", "-30", "+15"])
def test_integer_literals_at_eof(value):
    tokens = tokenize(value)

    assert tokens[0].type == TokenType.INTEGER
    assert tokens[0].value == value
    assert tokens[1].type == TokenType.EOF
