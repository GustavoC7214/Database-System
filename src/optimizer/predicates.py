"""Parse and estimate predicates emitted by the Module 3 SQL compiler.

This is a parser for compiler-generated conditions, not a general SQL parser.
Supported syntax: comparisons, AND, OR, NOT, parentheses, integer and
single-quoted string literals, and qualified/unqualified column names.
"""

import re
from dataclasses import dataclass
from typing import TypeAlias

from src.optimizer.selectivity import (
    DEFAULT_JOIN_SELECTIVITY,
    and_selectivity,
    comparison_selectivity,
    equijoin_selectivity,
    not_selectivity,
    or_selectivity,
)
from src.optimizer.statistics import ColumnStatistics

_TOKEN_PATTERN = re.compile(
    r"\s*(?:"
    r"(?P<string>'(?:''|[^'])*')"
    r"|(?P<integer>-?\d+)"
    r"|(?P<operator><=|>=|<>|!=|==|=|<|>)"
    r"|(?P<paren>[()])"
    r"|(?P<identifier>[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)"
    r")"
)

_REVERSED_OPERATORS = {
    "=": "=",
    "==": "==",
    "!=": "!=",
    "<>": "<>",
    "<": ">",
    "<=": ">=",
    ">": "<",
    ">=": "<=",
}


@dataclass(frozen=True, slots=True)
class ColumnRef:
    name: str


@dataclass(frozen=True, slots=True)
class LiteralValue:
    value: int | str


Operand: TypeAlias = ColumnRef | LiteralValue


@dataclass(frozen=True, slots=True)
class ComparisonPredicate:
    left: Operand
    operator: str
    right: Operand


@dataclass(frozen=True, slots=True)
class BooleanPredicate:
    operator: str
    left: "Predicate"
    right: "Predicate"


@dataclass(frozen=True, slots=True)
class NotPredicate:
    operand: "Predicate"


Predicate: TypeAlias = ComparisonPredicate | BooleanPredicate | NotPredicate


def _tokenize(source: str) -> list[str]:
    tokens: list[str] = []
    position = 0

    while position < len(source):
        if source[position:].isspace():
            break

        match = _TOKEN_PATTERN.match(source, position)
        if match is None:
            raise ValueError(
                f"Invalid predicate token at position {position}: "
                f"{source[position : position + 20]!r}"
            )

        tokens.append(match.group().strip())
        position = match.end()

    return tokens


class _PredicateParser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0

    def _peek(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _consume(self) -> str:
        token = self._peek()
        if token is None:
            raise ValueError("Unexpected end of predicate")
        self.position += 1
        return token

    def _accept(self, expected: str) -> bool:
        token = self._peek()
        if token is not None and token.upper() == expected:
            self.position += 1
            return True
        return False

    def _expect(self, expected: str) -> None:
        if not self._accept(expected):
            raise ValueError(f"Expected {expected!r}, got {self._peek()!r}")

    def parse(self) -> Predicate:
        result = self._parse_or()
        if self._peek() is not None:
            raise ValueError(f"Unexpected predicate token: {self._peek()!r}")
        return result

    def _parse_or(self) -> Predicate:
        left = self._parse_and()

        while self._accept("OR"):
            right = self._parse_and()
            left = BooleanPredicate("OR", left, right)

        return left

    def _parse_and(self) -> Predicate:
        left = self._parse_not()

        while self._accept("AND"):
            right = self._parse_not()
            left = BooleanPredicate("AND", left, right)

        return left

    def _parse_not(self) -> Predicate:
        if self._accept("NOT"):
            return NotPredicate(self._parse_not())

        if self._accept("("):
            result = self._parse_or()
            self._expect(")")
            return result

        return self._parse_comparison()

    def _parse_operand(self) -> Operand:
        token = self._consume()

        if token.startswith("'") and token.endswith("'"):
            return LiteralValue(token[1:-1].replace("''", "'"))

        if re.fullmatch(r"-?\d+", token):
            return LiteralValue(int(token))

        if re.fullmatch(
            r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*",
            token,
        ) and token.upper() not in {"AND", "OR", "NOT"}:
            return ColumnRef(token)

        raise ValueError(f"Invalid predicate operand: {token!r}")

    def _parse_comparison(self) -> ComparisonPredicate:
        left = self._parse_operand()
        operator = self._consume()

        if operator not in _REVERSED_OPERATORS:
            raise ValueError(f"Invalid comparison operator: {operator!r}")

        right = self._parse_operand()
        return ComparisonPredicate(left, operator, right)


def parse_predicate(source: str) -> Predicate:
    """Parse a Module 3 compiler-generated condition string."""
    if not source.strip():
        raise ValueError("Predicate cannot be empty")

    return _PredicateParser(_tokenize(source)).parse()


def _column_stats(
    name: str,
    columns: dict[str, ColumnStatistics],
) -> ColumnStatistics | None:
    """Resolve exact names, or unambiguous unqualified column names."""
    if name in columns:
        return columns[name]

    if "." in name:
        return None

    matches = [
        stats
        for qualified, stats in columns.items()
        if qualified.rsplit(".", 1)[-1] == name
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def _compare_literals(
    left: int | str,
    operator: str,
    right: int | str,
) -> bool:
    if operator in {"=", "=="}:
        return left == right
    if operator in {"!=", "<>"}:
        return left != right

    if type(left) is not type(right):
        raise ValueError("Cannot order literals of different types")

    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    return left >= right


def estimate_predicate(
    predicate: Predicate,
    columns: dict[str, ColumnStatistics],
    *,
    n_tuples: int | None = None,
) -> float:
    """Estimate predicate selectivity using available column statistics.

    Missing column statistics use Phase 2A fallback estimates.
    Boolean combinations assume statistical independence.
    """
    if isinstance(predicate, NotPredicate):
        return not_selectivity(
            estimate_predicate(predicate.operand, columns, n_tuples=n_tuples)
        )

    if isinstance(predicate, BooleanPredicate):
        left = estimate_predicate(predicate.left, columns, n_tuples=n_tuples)
        right = estimate_predicate(predicate.right, columns, n_tuples=n_tuples)

        if predicate.operator == "AND":
            return and_selectivity(left, right)
        if predicate.operator == "OR":
            return or_selectivity(left, right)

        raise ValueError(f"Unsupported Boolean operator: {predicate.operator}")

    left = predicate.left
    right = predicate.right
    operator = predicate.operator

    if isinstance(left, LiteralValue) and isinstance(right, LiteralValue):
        return float(_compare_literals(left.value, operator, right.value))

    if isinstance(left, ColumnRef) and isinstance(right, LiteralValue):
        return comparison_selectivity(
            _column_stats(left.name, columns),
            operator,
            right.value,
            n_tuples=n_tuples,
        )

    if isinstance(left, LiteralValue) and isinstance(right, ColumnRef):
        return comparison_selectivity(
            _column_stats(right.name, columns),
            _REVERSED_OPERATORS[operator],
            left.value,
            n_tuples=n_tuples,
        )

    if isinstance(left, ColumnRef) and isinstance(right, ColumnRef):
        if left.name == right.name:
            return float(operator in {"=", "==", "<=", ">="})

        if operator in {"=", "=="}:
            return equijoin_selectivity(
                _column_stats(left.name, columns),
                _column_stats(right.name, columns),
            )

        if operator in {"!=", "<>"}:
            return not_selectivity(
                equijoin_selectivity(
                    _column_stats(left.name, columns),
                    _column_stats(right.name, columns),
                )
            )

        return DEFAULT_JOIN_SELECTIVITY

    raise TypeError(f"Unsupported predicate: {predicate!r}")


def estimate_condition(
    source: str,
    columns: dict[str, ColumnStatistics],
    *,
    n_tuples: int | None = None,
) -> float:
    """Parse a condition string and estimate its selectivity."""
    return estimate_predicate(
        parse_predicate(source),
        columns,
        n_tuples=n_tuples,
    )
