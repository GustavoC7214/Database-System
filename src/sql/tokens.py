"""Token definitions for the Module 3 SQL front end."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    IDENTIFIER = auto()
    INTEGER = auto()
    STRING = auto()
    KEYWORD = auto()
    OPERATOR = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    DOT = auto()
    SEMICOLON = auto()
    STAR = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: str
    line: int
    column: int


KEYWORDS = frozenset(
    {
        "SELECT",
        "DISTINCT",
        "FROM",
        "WHERE",
        "GROUP",
        "BY",
        "HAVING",
        "ORDER",
        "LIMIT",
        "ASC",
        "DESC",
        "AS",
        "JOIN",
        "ON",
        "AND",
        "OR",
        "NOT",
        "UNION",
        "ALL",
        "INTERSECT",
        "EXCEPT",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "CREATE",
        "TABLE",
        "INSERT",
        "INTO",
        "VALUES",
        "INT",
        "VARCHAR",
    }
)
