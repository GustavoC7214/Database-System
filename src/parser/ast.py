from dataclasses import dataclass, field
from enum import Enum

RelationValue = int | str

class ComparisonOperator(Enum):
    EQUAL = "="
    NOT_EQUAL = "!="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="


class BooleanOperator(Enum):
    AND = "and"
    OR = "or"


class BinaryOperator(Enum):
    UNION = "union"
    INTERSECT = "intersect"
    MINUS = "minus"
    TIMES = "times"


class SortDictionary(Enum):
    ASC = "asc"
    DESC = "desc"


class ASTNode:
    pass


class Expression(ASTNode):
    pass


class Condition(ASTNode):
    pass


class Operand(ASTNode):
    pass


@dataclass
class RelationReference(Expression):
    name: str


@dataclass
class AttributeReference(Operand):
    name: str
    relation: str | None = None


@dataclass
class NumberLiteral(Operand):
    value: int


@dataclass
class StringLiteral(Operand):
    value: str


@dataclass
class Comparison(Condition):
    left: Operand
    operator: ComparisonOperator
    right: Operand


@dataclass
class Not(Condition):
    condition: Condition


@dataclass
class BooleanBinaryCondition(Condition):
    left: Condition
    operator: BooleanOperator
    right: Condition


@dataclass
class Select(Expression):
    condition: Condition
    expression: Expression


@dataclass
class Project(Expression):
    attributes: list[AttributeReference]
    expression: Expression


@dataclass
class Rename(Expression):
    new_name: str
    expression: Expression
    attribute_renames: dict[str, str] = field(default_factory=dict)


@dataclass
class BinaryExpression(Expression):
    left: Expression
    operator: BinaryOperator
    right: Expression


@dataclass
class Join(Expression):
    left: Expression
    condition: Condition
    right: Expression


@dataclass
class RelationDefinition(ASTNode):
    name: str
    attributes: list[str]
    rows: list[list[RelationValue]]


@dataclass
class Sort(Expression):
    attribute: AttributeReference
    direction: SortDictionary
    expression: Expression
    