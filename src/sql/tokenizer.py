"""Handwritten SQL tokenizer for COMP 3005 Module 3."""

from collections.abc import Iterator

from src.sql.tokens import KEYWORDS, Token, TokenType


class SQLLexicalError(ValueError):
    """A lexical error with a source location."""

    def __init__(self, message: str, line: int, column: int) -> None:
        self.line = line
        self.column = column
        super().__init__(f"error: lexical: {message} at line {line}, column {column}")


class SQLTokenizer:
    """Scan the supported SQL subset without regex or parser generators."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1

    def _peek(self, offset: int = 0) -> str:
        index = self.position + offset
        if index >= len(self.source):
            return ""
        return self.source[index]

    def _advance(self) -> str:
        char = self._peek()

        if not char:
            return ""

        self.position += 1

        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1

        return char

    def _skip_whitespace_and_comments(self) -> None:
        while True:
            if self._peek() in (" ", "\t", "\r", "\n"):
                self._advance()
                continue

            if self._peek() == "-" and self._peek(1) == "-":
                while self._peek() not in ("", "\n"):
                    self._advance()
                continue

            break

    def _identifier(self) -> Token:
        line, column = self.line, self.column
        chars = []

        while self._peek().isascii() and (
            self._peek().isalnum() or self._peek() == "_"
        ):
            chars.append(self._advance())

        value = "".join(chars)

        if value.upper() in KEYWORDS:
            return Token(TokenType.KEYWORD, value.upper(), line, column)

        return Token(TokenType.IDENTIFIER, value, line, column)

    def _integer(self) -> Token:
        line, column = self.line, self.column
        chars = []

        if self._peek() in ("+", "-"):
            chars.append(self._advance())

        while self._peek() and self._peek() in "0123456789":
            chars.append(self._advance())

        return Token(TokenType.INTEGER, "".join(chars), line, column)

    def _string(self) -> Token:
        line, column = self.line, self.column
        self._advance()

        chars = []

        while True:
            char = self._peek()

            if char == "":
                raise SQLLexicalError("unterminated string literal", line, column)

            if char == "'":
                self._advance()

                if self._peek() == "'":
                    self._advance()
                    chars.append("'")
                    continue

                break

            chars.append(self._advance())

        return Token(TokenType.STRING, "".join(chars), line, column)

    def tokens(self) -> Iterator[Token]:
        punctuation = {
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            ",": TokenType.COMMA,
            ".": TokenType.DOT,
            ";": TokenType.SEMICOLON,
            "*": TokenType.STAR,
        }

        while True:
            self._skip_whitespace_and_comments()

            char = self._peek()
            line, column = self.line, self.column

            if char == "":
                yield Token(TokenType.EOF, "", line, column)
                return

            if char.isascii() and (char.isalpha() or char == "_"):
                yield self._identifier()
                continue

            if char == "'":
                yield self._string()
                continue

            if char in ("+", "-") and self._peek(1) in "0123456789":
                yield self._integer()
                continue

            if char in "0123456789":
                yield self._integer()
                continue

            if char in punctuation:
                self._advance()
                yield Token(punctuation[char], char, line, column)
                continue

            if char in ("<", ">"):
                operator = self._advance()

                if self._peek() in ("=", ">") and (
                    operator == "<" or self._peek() == "="
                ):
                    operator += self._advance()

                yield Token(TokenType.OPERATOR, operator, line, column)
                continue

            if char == "=":
                self._advance()
                yield Token(TokenType.OPERATOR, "=", line, column)
                continue

            raise SQLLexicalError(f"unexpected character {char!r}", line, column)


def tokenize(source: str) -> list[Token]:
    """Tokenize a SQL source string, including the final EOF token."""
    return list(SQLTokenizer(source).tokens())
