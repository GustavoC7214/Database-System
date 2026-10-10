import pytest

from src.lexer.token import TokenType
from src.lexer.tokenizer import LexicalError, Tokenizer


def test_no_whitespace_expression():
    source = "select[x1=3](R)"
    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()
    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "x1"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.NUMBER, "3"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_expression_with_whitespace():
    source = "select [ x1 = 3 ] ( R )"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "x1"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.NUMBER, "3"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected    

def test_greater_than_or_equal_operator():
    source = "select[Age>=30](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "Age"),
        (TokenType.COMPARISON_OPERATOR, ">="),
        (TokenType.NUMBER, "30"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_greater_than_negative_number():
    source = "select[Age>-30](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "Age"),
        (TokenType.COMPARISON_OPERATOR, ">"),
        (TokenType.NUMBER, "-30"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_parenthesis_inside_string():
    source = "select[Name='Bob)'](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "Name"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.STRING, "Bob)"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_comma_inside_string():
    source = "select[Name='a,b'](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "Name"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.STRING, "a,b"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_doubled_quote_inside_string():
    source = "select[Name='O''Brien'](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "Name"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.STRING, "O'Brien"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_keyword_as_attribute():
    source = "select[union=3](R)"

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "select"),
        (TokenType.LBRACKET, "["),
        (TokenType.IDENTIFIER, "union"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.NUMBER, "3"),
        (TokenType.RBRACKET, "]"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "R"),
        (TokenType.RPAREN, ")"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_unterminated_string():
    source = "select[Name='Bob](R)"

    with pytest.raises(LexicalError) as error:
        Tokenizer(source).tokenize()

    assert "line 1, column 13" in str(error.value)

def test_alphanumeric_relation_value_is_bare_string():
    source = """R (Value) = {
123abc
}"""

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "R"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "Value"),
        (TokenType.RPAREN, ")"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.LBRACE, "{"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.BARE_STRING, "123abc"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.RBRACE, "}"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_quoted_only_tuple_emits_newline():
    source = """Names (Name) = {
'John Smith'
}"""

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "Names"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "Name"),
        (TokenType.RPAREN, ")"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.LBRACE, "{"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.STRING, "John Smith"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.RBRACE, "}"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_comment_only_line_does_not_emit_newline():
    source = """R (Value) = {
first
// this is a comment
second
}"""

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "R"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "Value"),
        (TokenType.RPAREN, ")"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.LBRACE, "{"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.BARE_STRING, "first"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.BARE_STRING, "second"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.RBRACE, "}"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_inline_comment_without_whitespace():
    source = """R (Value) = {
first// comment
}"""

    tokenizer = Tokenizer(source)
    tokens = tokenizer.tokenize()

    actual = [(token.type, token.value) for token in tokens]

    expected = [
        (TokenType.IDENTIFIER, "R"),
        (TokenType.LPAREN, "("),
        (TokenType.IDENTIFIER, "Value"),
        (TokenType.RPAREN, ")"),
        (TokenType.COMPARISON_OPERATOR, "="),
        (TokenType.LBRACE, "{"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.BARE_STRING, "first"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.RBRACE, "}"),
        (TokenType.EOF, ""),
    ]

    assert actual == expected

def test_non_ascii_identifier_raises_lexical_error():
    source = "Employées"

    with pytest.raises(LexicalError) as error:
        Tokenizer(source).tokenize()

    assert "line 1, column 7" in str(error.value)

def test_identifier_cannot_start_with_underscore():
    source = "_Employee"

    with pytest.raises(LexicalError) as error:
        Tokenizer(source).tokenize()

    assert "line 1, column 1" in str(error.value)

def test_standalone_exclamation_mark_raises_lexical_error():
    source = "select[Age!30](R)"

    with pytest.raises(LexicalError) as error:
        Tokenizer(source).tokenize()

    assert "line 1, column 11" in str(error.value)