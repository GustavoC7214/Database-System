"""Immutable abstract syntax tree nodes for the Module 3 SQL subset."""

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    qualifier: str | None = None
    line: int = field(default=1, compare=False)
    column: int = field(default=1, compare=False)


@dataclass(frozen=True, slots=True)
class Literal:
    value: int | str


@dataclass(frozen=True, slots=True)
class Aggregate:
    function: str
    argument: Column | None  # None represents COUNT(*).


Expression: TypeAlias = Column | Literal | Aggregate


@dataclass(frozen=True, slots=True)
class Comparison:
    left: Expression
    operator: str
    right: Expression


@dataclass(frozen=True, slots=True)
class Logical:
    operator: str
    left: "Condition"
    right: "Condition"


@dataclass(frozen=True, slots=True)
class Negation:
    operand: "Condition"


Condition: TypeAlias = Comparison | Logical | Negation


@dataclass(frozen=True, slots=True)
class SelectItem:
    expression: Column | Aggregate
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class SortItem:
    column: Column
    direction: str = "ASC"


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    alias: str | None = None
    line: int = field(default=1, compare=False)
    column: int = field(default=1, compare=False)


@dataclass(frozen=True, slots=True)
class DerivedTable:
    query: "Query"
    alias: str
    line: int = field(default=1, compare=False)
    column: int = field(default=1, compare=False)


TableReference: TypeAlias = Table | DerivedTable


@dataclass(frozen=True, slots=True)
class FromExtension:
    kind: str  # CROSS or JOIN
    table: TableReference
    condition: Condition | None = None


@dataclass(frozen=True, slots=True)
class Select:
    distinct: bool
    columns: tuple[SelectItem, ...] | None  # None represents *.
    source: TableReference
    extensions: tuple[FromExtension, ...] = ()
    where: Condition | None = None
    group_by: tuple[Column, ...] = ()
    having: Condition | None = None
    order_by: tuple[SortItem, ...] = ()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class SetOperation:
    operator: str
    left: "Query"
    right: "Query"


Query: TypeAlias = Select | SetOperation


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    data_type: str
    length: int | None = None


@dataclass(frozen=True, slots=True)
class CreateTable:
    name: str
    columns: tuple[ColumnDefinition, ...]


@dataclass(frozen=True, slots=True)
class Insert:
    table: str
    values: tuple[Literal, ...]


Statement: TypeAlias = CreateTable | Insert | Query
