import pytest

from src.engine.database import Database
from src.engine.evaluator import Evaluator
from src.engine.relation import Attribute, Relation, Row
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
    RelationReference,
    Rename,
    Select,
    Sort,
    SortDictionary,
    StringLiteral,
)


def test_evaluate_relation_reference():
    database = Database()
    employees = Relation("Employees", [Attribute("Employees", "EID")], [])
    database.add_relation(employees)

    evaluator = Evaluator(database)
    expression = RelationReference("Employees")
    result = evaluator.evaluate(expression)
    assert result is employees


def test_evaluate_undefined_relation():
    database = Database()
    evaluator = Evaluator(database)
    expression = RelationReference("Managers")

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_resolve_unqualified_attribute():
    database = Database()
    evaluator = Evaluator(database)
    attributes = [
        Attribute("Employees", "EID"),
        Attribute("Employees", "Name"),
        Attribute("Employees", "Age"),
    ]
    employees = Relation("Employees", attributes, [])
    reference = AttributeReference(name="Age")

    assert evaluator.resolve_attribute(reference, employees) == 2


def test_resolve_qualified_attribute():
    database = Database()
    evaluator = Evaluator(database)
    attributes = [
        Attribute("Employees", "EID"),
        Attribute("Employees", "Name"),
        Attribute("Employees", "Age"),
    ]
    employees = Relation("Employees", attributes, [])
    reference = AttributeReference(name="Age", relation="Employees")
    

    assert evaluator.resolve_attribute(reference, employees) == 2


def test_resolve_undefined_attribute():
    database = Database()
    evaluator = Evaluator(database)
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "EID"),
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [],
    )
    reference = AttributeReference(name="Salary")

    with pytest.raises(NameError):
        evaluator.resolve_attribute(reference, employees)


def test_resolve_ambiguous_attribute():
    database = Database()
    evaluator = Evaluator(database)
    attributes = [
        Attribute("Employees", "DID"),
        Attribute("Departments", "DID"),
    ]
    relation = Relation("Employees", attributes, [])
    reference = AttributeReference(name="DID")

    with pytest.raises(NameError):
        evaluator.resolve_attribute(reference, relation)


def test_evaluate_number_literal():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation("Employees", [], [])
    row = Row([])
    operand = NumberLiteral(25)

    assert evaluator.evaluate_operand(operand, relation, row) == 25


def test_evaluate_string_literal():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation("Employees", [], [])
    row = Row([])
    operand = StringLiteral("John")

    assert evaluator.evaluate_operand(operand, relation, row) == "John"


def test_evaluate_attribute_reference():
    database = Database()
    evaluator = Evaluator(database)
    attributes = [
        Attribute("Employees", "EID"),
        Attribute("Employees", "Name"),
        Attribute("Employees", "Age"),
    ]
    relation = Relation("Employees", attributes, [])
    row = Row(["E1", "John", 32])
    operand = AttributeReference(name="Age")

    assert evaluator.evaluate_operand(operand, relation, row) == 32


def test_evaluate_greater_than_condition():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Age")],
        [],
    )
    row = Row([32])
    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.GREATER_THAN,
        right=NumberLiteral(25),
    )
    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row([20])
    assert evaluator.evaluate_condition(condition, relation, row) is False
    row = Row([25])
    assert evaluator.evaluate_condition(condition, relation, row) is False

    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        right=NumberLiteral(25),
    )
    row = Row([25])

    assert evaluator.evaluate_condition(condition, relation, row) is True


def test_evaluate_comparison_type_mismatch():
    database = Database()
    evaluator = Evaluator(database)
    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.GREATER_THAN,
        right=StringLiteral("25"),
    )
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Age")],
        [],
    )
    row = Row([25])

    with pytest.raises(TypeError):
        evaluator.evaluate_condition(condition, relation, row)


def test_evaluate_less_than_condition():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Age")],
        [],
    )
    row = Row([20])
    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.LESS_THAN,
        right=NumberLiteral(25),
    )
    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row([25])
    assert evaluator.evaluate_condition(condition, relation, row) is False

    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        right=NumberLiteral(25),
    )
    row = Row([25])

    assert evaluator.evaluate_condition(condition, relation, row) is True


def test_evaluate_equal_condition():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Age")],
        [],
    )
    row = Row([25])

    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.EQUAL,
        right=NumberLiteral(25),
    )

    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row([30])
    assert evaluator.evaluate_condition(condition, relation, row) is False

    condition = Comparison(
        left=AttributeReference(name="Age"),
        operator=ComparisonOperator.NOT_EQUAL,
        right=NumberLiteral(25),
    )
    row = Row([30])
    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row([25])
    assert evaluator.evaluate_condition(condition, relation, row) is False


def test_evaluate_string_equality():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Name")],
        [],
    )
    row = Row(["John"])
    condition = Comparison(
        left=AttributeReference(name="Name"),
        operator=ComparisonOperator.EQUAL,
        right=StringLiteral("John"),
    )
    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row(["Jane"])
    assert evaluator.evaluate_condition(condition, relation, row) is False


def test_evaluate_not_condition():
    database = Database()
    evaluator = Evaluator(database)
    relation = Relation(
        "Employees",
        [Attribute("Employees", "Age")],
        [],
    )
    condition = Not(
        Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(25),
        )
    )
    row = Row([20])

    assert evaluator.evaluate_condition(condition, relation, row) is True
    row = Row([32])
    assert evaluator.evaluate_condition(condition, relation, row) is False


def test_evaluate_and_condition():
    evaluator = Evaluator(Database())
    relation = Relation(
        "Employees",
        [
            Attribute("Employees", "Age"),
            Attribute("Employees", "Name"),
        ],
        [],
    )

    condition = BooleanBinaryCondition(
        left=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(25),
        ),
        operator=BooleanOperator.AND,
        right=Comparison(
            left=AttributeReference(name="Name"),
            operator=ComparisonOperator.EQUAL,
            right=StringLiteral("John"),
        ),
    )

    assert evaluator.evaluate_condition(condition, relation, Row([32, "John"])) is True
    assert evaluator.evaluate_condition(condition, relation, Row([32, "Alice"])) is False
    assert evaluator.evaluate_condition(condition, relation, Row([20, "John"])) is False


def test_evaluate_or_condition():
    evaluator = Evaluator(Database())
    relation = Relation(
        "Employees",
        [
            Attribute("Employees", "Age"),
            Attribute("Employees", "Name"),
        ],
        [],
    )

    condition = BooleanBinaryCondition(
        left=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(25),
        ),
        operator=BooleanOperator.OR,
        right=Comparison(
            left=AttributeReference(name="Name"),
            operator=ComparisonOperator.EQUAL,
            right=StringLiteral("John"),
        ),
    )

    assert evaluator.evaluate_condition(condition, relation, Row([32, "John"])) is True
    assert evaluator.evaluate_condition(condition, relation, Row([32, "Alice"])) is True
    assert evaluator.evaluate_condition(condition, relation, Row([20, "John"])) is True
    assert evaluator.evaluate_condition(condition, relation, Row([20, "Alice"])) is False


def test_evaluate_select():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(25),
        ),
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == employees.attributes
    assert result.rows == [Row(["John", 32]), Row(["Bob", 28])]
    assert len(employees.rows) == 3

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(50),
        ),
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == employees.attributes
    assert result.rows == []

    expression = Select (
        condition = Comparison(
            left = AttributeReference(name = "Name"),
            operator = ComparisonOperator.EQUAL,
            right = StringLiteral("Bob")
        ),
        expression = Select(
            condition = Comparison(
                left = AttributeReference(name = "Age"),
                operator = ComparisonOperator.GREATER_THAN,
                right = NumberLiteral(25)
            ),
            expression = RelationReference("Employees")
        )
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == employees.attributes
    assert result.rows == [Row(["Bob", 28])]


def test_evaluate_project():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="Name")],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Employees", "Name")]
    assert result.rows == [
        Row(["John"]),
        Row(["Alice"]),
        Row(["Bob"]),
    ]
    assert len(employees.attributes) == 2


def test_evaluate_project_multiple_columns():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
            Attribute("Employees", "City"),
        ],
        [Row(["John", 32, "Ottawa"])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[
            AttributeReference(name="City"),
            AttributeReference(name="Name"),
        ],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "City"),
        Attribute("Employees", "Name"),
    ]
    assert result.rows == [Row(["Ottawa", "John"])]


def test_evaluate_project_remove_duplicates():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["John", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="Name")],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [Row(["John"]), Row(["Alice"])]


def test_evaluate_project_over_select():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="Name")],
        expression=Select(
            condition=Comparison(
                left=AttributeReference(name="Age"),
                operator=ComparisonOperator.GREATER_THAN,
                right=NumberLiteral(25),
            ),
            expression=RelationReference("Employees"),
        ),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Employees", "Name")]
    assert result.rows == [Row(["John"]), Row(["Bob"])]


def test_evaluate_project_undefined_attribute():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="Salary")],
        expression=RelationReference("Employees"),
    )

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_project_ambiguous_attribute():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [Row([10, 20])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="DID")],
        expression=RelationReference("Employees"),
    )

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_select_over_project_missing_attribute():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="Age"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(25),
        ),
        expression=Project(
            attributes=[AttributeReference(name="Name")],
            expression=RelationReference("Employees"),
        ),
    )

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_select_over_project():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="Name"),
            operator=ComparisonOperator.EQUAL,
            right=StringLiteral("John"),
        ),
        expression=Project(
            attributes=[AttributeReference(name="Name")],
            expression=RelationReference("Employees"),
        ),
    )
    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Employees", "Name")]
    assert result.rows == [Row(["John"])]

def test_evaluate_project_qualified_attributes():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [Row([10, 20])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="DID", relation="Employees")],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Employees", "DID")]
    assert result.rows == [Row([10])]


def test_evaluate_project_departments_qualified_attribute():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [Row([10, 20])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[AttributeReference(name="DID", relation="Departments")],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Departments", "DID")]
    assert result.rows == [Row([20])]

def test_evaluate_project_both_qualified_attributes():
    database = Database()
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [Row([10, 20])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Project(
        attributes=[
            AttributeReference(name="DID", relation="Departments"),
            AttributeReference(name="DID", relation="Employees"),
        ],
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Departments", "DID"),
        Attribute("Employees", "DID"),
    ]
    assert result.rows == [Row([20, 10])]

def test_evaluate_sort_ascending():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute = AttributeReference(name ="Age"),
        direction = SortDictionary.ASC,
        expression = RelationReference("Employees")
    )
    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Alice", 20]),
        Row(["Bob", 28]),
        Row(["John", 32]),
    ]
    assert employees.rows == [
        Row(["John", 32]),
        Row(["Alice", 20]),
        Row(["Bob", 28]),
    ]


def test_evaluate_sort_descending():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute = AttributeReference(name ="Age"),
        direction = SortDictionary.DESC,
        expression = RelationReference("Employees")
    )
    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["John", 32]),
        Row(["Bob", 28]),
        Row(["Alice", 20]),
    ]


def test_evaluate_sort_undefined_attribute():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 32]),
            Row(["Alice", 20]),
            Row(["Bob", 28]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="Salary"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )
    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_sort_ambiguous_attribute():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [Row([10, 20])],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="DID"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_sort_qualified_attribute():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "DID"),
            Attribute("Departments", "DID"),
        ],
        [
            Row([30, 20]),
            Row([10, 40]),
            Row([20, 10]),
        ],
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="DID", relation="Departments"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)
    
    assert result.rows == [
        Row([20, 10]),
        Row([30, 20]),
        Row([10, 40]),
    ]


def test_evaluate_sort_string_attribute():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Empolyees", "Age"),
        ],
    [
        Row(["John", 32]),
        Row(["Alice", 20]),
        Row(["Bob", 28]),
    ]
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="Name"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)
    
    assert result.rows == [
        Row(["Alice", 20]),
        Row(["Bob", 28]),
        Row(["John", 32]),
    ]


def test_evaluate_sort_empty_relation():
    database = Database()
    
    employees = Relation(
        "Employees",
        [Attribute("Employees", "Age"),],
        []
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="Age"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)
    
    assert result.rows == []


def test_evaluate_sort_duplicates_values():
    database = Database()
    
    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 25]),
            Row(["Alice", 20]),
            Row(["Bob", 25]),
        ]
    )
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = Sort(
        attribute=AttributeReference(name="Age"),
        direction=SortDictionary.ASC,
        expression=RelationReference("Employees"),
    )

    result = evaluator.evaluate(expression)
    
    assert result.rows == [
        Row(["Alice", 20]),
        Row(["John", 25]),
        Row(["Bob", 25]),
    ]


def test_evaluate_cartesian_product():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "Name")],
        [Row(["John"]), Row(["Alice"])],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "Department")],
        [Row(["IT"]), Row(["HR"])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Employees"),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "Name"),
        Attribute("Departments", "Department"),
    ]

    assert result.rows == [
        Row(["John", "IT"]),
        Row(["John", "HR"]),
        Row(["Alice", "IT"]),
        Row(["Alice", "HR"]),
    ]


def test_evaluate_cartesian_product_empty_relation():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "Name")],
        [Row(["John"]), Row(["Alice"])],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "Department")],
        [],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Employees"),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "Name"),
        Attribute("Departments", "Department"),
    ]
    assert result.rows == []


def test_evaluate_cartesian_product_empty_left_relation():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "Name")],
        [],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "Department")],
        [Row(["IT"]), Row(["HR"])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Employees"),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "Name"),
        Attribute("Departments", "Department"),
    ]
    assert result.rows == []


def test_evaluate_cartesian_product_multiple_attributes():
    database = Database()

    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 25]),
            Row(["Alice", 30]),
        ],
    )

    departments = Relation(
        "Departments",
        [
            Attribute("Departments", "DID"),
            Attribute("Departments", "Department"),
        ],
        [
            Row([1, "IT"]),
            Row([2, "HR"]),
        ],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Employees"),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "Name"),
        Attribute("Employees", "Age"),
        Attribute("Departments", "DID"),
        Attribute("Departments", "Department"),
    ]

    assert result.rows == [
        Row(["John", 25, 1, "IT"]),
        Row(["John", 25, 2, "HR"]),
        Row(["Alice", 30, 1, "IT"]),
        Row(["Alice", 30, 2, "HR"]),
    ]


def test_evaluate_cartesian_product_over_select():
    database = Database()

    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "Age"),
        ],
        [
            Row(["John", 25]),
            Row(["Alice", 30]),
            Row(["Bob", 35]),
        ],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "Department")],
        [Row(["IT"]), Row(["HR"])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=Select(
            condition=Comparison(
                left=AttributeReference(name="Age"),
                operator=ComparisonOperator.GREATER_THAN,
                right=NumberLiteral(30),
            ),
            expression=RelationReference("Employees"),
        ),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Bob", 35, "IT"]),
        Row(["Bob", 35, "HR"]),
    ]


def test_evaluate_cartesian_product_duplicate_attribute_names():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "DID")],
        [Row([10])],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "DID")],
        [Row([20])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Employees"),
        operator=BinaryOperator.TIMES,
        right=RelationReference("Departments"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Employees", "DID"),
        Attribute("Departments", "DID"),
    ]
    assert result.rows == [Row([10, 20])]


def test_evaluate_select_over_cartesian_product_ambiguous_attribute():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "DID")],
        [Row([10])],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "DID")],
        [Row([20])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="DID"),
            operator=ComparisonOperator.EQUAL,
            right=NumberLiteral(10),
        ),
        expression=BinaryExpression(
            left=RelationReference("Employees"),
            operator=BinaryOperator.TIMES,
            right=RelationReference("Departments"),
        ),
    )

    with pytest.raises(NameError):
        evaluator.evaluate(expression)


def test_evaluate_select_over_cartesian_product_qualified_attribute():
    database = Database()

    employees = Relation(
        "Employees",
        [Attribute("Employees", "DID")],
        [Row([10]), Row([20])],
    )

    departments = Relation(
        "Departments",
        [Attribute("Departments", "DID")],
        [Row([20])],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="DID", relation="Employees"),
            operator=ComparisonOperator.EQUAL,
            right=NumberLiteral(10),
        ),
        expression=BinaryExpression(
            left=RelationReference("Employees"),
            operator=BinaryOperator.TIMES,
            right=RelationReference("Departments"),
        ),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [Row([10, 20])]


def test_evaluate_select_matching_attributes_over_cartesian_product():
    database = Database()

    employees = Relation(
        "Employees",
        [
            Attribute("Employees", "Name"),
            Attribute("Employees", "DID"),
        ],
        [
            Row(["John", 10]),
            Row(["Alice", 20]),
            Row(["Bob", 10]),
        ],
    )

    departments = Relation(
        "Departments",
        [
            Attribute("Departments", "DID"),
            Attribute("Departments", "Department"),
        ],
        [
            Row([10, "IT"]),
            Row([20, "HR"]),
        ],
    )

    database.add_relation(employees)
    database.add_relation(departments)

    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="DID", relation="Employees"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="DID", relation="Departments"),
        ),
        expression=BinaryExpression(
            left=RelationReference("Employees"),
            operator=BinaryOperator.TIMES,
            right=RelationReference("Departments"),
        ),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["John", 10, 10, "IT"]),
        Row(["Alice", 20, 20, "HR"]),
        Row(["Bob", 10, 10, "IT"]),
    ]


def test_evaluate_theta_join():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "ChapterID"),
        ],
        [
            Row(["Alice", 1]),
            Row(["Bob", 2]),
        ],
    )

    chapters = Relation(
        "Chapter",
        [
            Attribute("Chapter", "ID"),
            Attribute("Chapter", "Location"),
        ],
        [
            Row([1, "Ottawa"]),
            Row([3, "Toronto"]),
        ],
    )

    database.add_relation(members)
    database.add_relation(chapters)
    evaluator = Evaluator(database)

    expression = Join(
        left=RelationReference("Member"),
        condition=Comparison(
            left=AttributeReference(name="ChapterID", relation="Member"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="ID", relation="Chapter"),
        ),
        right=RelationReference("Chapter"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Member", "Name"),
        Attribute("Member", "ChapterID"),
        Attribute("Chapter", "ID"),
        Attribute("Chapter", "Location"),
    ]
    assert result.rows == [Row(["Alice", 1, 1, "Ottawa"])]


def test_evaluate_theta_join_no_matches():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "ChapterID")],
        [Row([1]), Row([2])],
    )

    chapters = Relation(
        "Chapter",
        [Attribute("Chapter", "ID")],
        [Row([3]), Row([4])],
    )

    database.add_relation(members)
    database.add_relation(chapters)
    evaluator = Evaluator(database)

    expression = Join(
        left=RelationReference("Member"),
        condition=Comparison(
            left=AttributeReference(name="ChapterID", relation="Member"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="ID", relation="Chapter"),
        ),
        right=RelationReference("Chapter"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("Member", "ChapterID"),
        Attribute("Chapter", "ID"),
    ]
    assert result.rows == []


def test_evaluate_theta_join_multiple_matches():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "ChapterID"),
        ],
        [
            Row(["Alice", 1]),
            Row(["Bob", 2]),
            Row(["Charlie", 1]),
        ],
    )

    chapters = Relation(
        "Chapter",
        [
            Attribute("Chapter", "ID"),
            Attribute("Chapter", "Location"),
        ],
        [
            Row([1, "Ottawa"]),
            Row([2, "Toronto"]),
        ],
    )

    database.add_relation(members)
    database.add_relation(chapters)
    evaluator = Evaluator(database)

    expression = Join(
        left=RelationReference("Member"),
        condition=Comparison(
            left=AttributeReference(name="ChapterID", relation="Member"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="ID", relation="Chapter"),
        ),
        right=RelationReference("Chapter"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Alice", 1, 1, "Ottawa"]),
        Row(["Bob", 2, 2, "Toronto"]),
        Row(["Charlie", 1, 1, "Ottawa"]),
    ]


def test_evaluate_union():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Charlie"]), Row(["David"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Member", "Name")]
    assert result.rows == [
        Row(["Alice"]),
        Row(["Bob"]),
        Row(["Charlie"]),
        Row(["David"]),
    ]


def test_evaluate_union_removes_duplicates():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["Charlie"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Alice"]),
        Row(["Bob"]),
        Row(["Charlie"]),
    ]


def test_evaluate_union_incompatible_attribute_counts():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row(["Alice", 25])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError):
        evaluator.evaluate(expression)


def test_evaluate_union_empty_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["Charlie"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Member", "Name")]
    assert result.rows == [
        Row(["Bob"]),
        Row(["Charlie"]),
    ]


def test_evaluate_union_different_attribute_names():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "FullName")],
        [Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="attribute names differ"):
        evaluator.evaluate(expression)


def test_evaluate_union_incompatible_data_types():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row(["Alice", 25])],
    )

    employees = Relation(
        "Employee",
        [
            Attribute("Employee", "FullName"),
            Attribute("Employee", "Years"),
        ],
        [Row(["Bob", "Thirty"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="not union-compatible"):
        evaluator.evaluate(expression)


def test_evaluate_union_compatible_data_types():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row(["Alice", 25])],
    )

    employees = Relation(
        "Employee",
        [
            Attribute("Employee", "Name"),
            Attribute("Employee", "Age"),
        ],
        [Row(["Bob", 30])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.UNION,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == members.attributes
    assert result.rows == [
        Row(["Alice", 25]),
        Row(["Bob", 30]),
    ]


def test_evaluate_intersection():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"]), Row(["Charlie"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["Charlie"]), Row(["David"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Member", "Name")]
    assert result.rows == [
        Row(["Bob"]),
        Row(["Charlie"]),
    ]


def test_evaluate_intersection_no_matches():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Charlie"]), Row(["David"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == []


def test_evaluate_intersection_removes_duplicates():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [Row(["Bob"])]


def test_evaluate_intersection_empty_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["Charlie"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Member", "Name")]
    assert result.rows == []


def test_evaluate_intersection_incompatible_attribute_counts():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row(["Alice", 25])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Alice"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="not union-compatible"):
        evaluator.evaluate(expression)


def test_evaluate_intersection_incompatible_data_types():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Age")],
        [Row([25])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Age")],
        [Row(["25"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.INTERSECT,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="not union-compatible"):
        evaluator.evaluate(expression)


def test_evaluate_difference():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"]), Row(["Charlie"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"]), Row(["David"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [Attribute("Member", "Name")]
    assert result.rows == [
        Row(["Alice"]),
        Row(["Charlie"]),
    ]


def test_evaluate_difference_no_matches():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Charlie"]), Row(["David"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Alice"]),
        Row(["Bob"]),
    ]


def test_evaluate_difference_all_matches():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Alice"]), Row(["Bob"]), Row(["Charlie"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == []


def test_evaluate_difference_removes_duplicates():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [Row(["Alice"])]


def test_evaluate_difference_empty_left_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == []


def test_evaluate_difference_empty_right_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"]), Row(["Bob"])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row(["Alice"]),
        Row(["Bob"]),
    ]


def test_evaluate_difference_incompatible_attribute_counts():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row(["Alice", 25])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Name")],
        [Row(["Bob"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="not union-compatible"):
        evaluator.evaluate(expression)


def test_evaluate_difference_incompatible_data_types():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Age")],
        [Row([25])],
    )

    employees = Relation(
        "Employee",
        [Attribute("Employee", "Age")],
        [Row(["25"])],
    )

    database.add_relation(members)
    database.add_relation(employees)
    evaluator = Evaluator(database)

    expression = BinaryExpression(
        left=RelationReference("Member"),
        operator=BinaryOperator.MINUS,
        right=RelationReference("Employee"),
    )

    with pytest.raises(ValueError, match="not union-compatible"):
        evaluator.evaluate(expression)


def test_evaluate_rename_relation():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Id"),
            Attribute("Member", "Name"),
        ],
        [
            Row([1, "Alice"]),
            Row([2, "Bob"]),
        ],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Rename(
        new_name="M1",
        expression=RelationReference("Member"),
    )

    result = evaluator.evaluate(expression)

    assert result.name == "M1"
    assert result.attributes == [
        Attribute("M1", "Id"),
        Attribute("M1", "Name"),
    ]
    assert result.rows == [
        Row([1, "Alice"]),
        Row([2, "Bob"]),
    ]


def test_evaluate_rename_selected_attributes():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Id"),
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [Row([1, "Alice", 25])],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Rename(
        new_name="M1",
        expression=RelationReference("Member"),
        attribute_renames={
            "Id": "MemberId",
            "Name": "MemberName",
        },
    )

    result = evaluator.evaluate(expression)

    assert result.name == "M1"
    assert result.attributes == [
        Attribute("M1", "MemberId"),
        Attribute("M1", "MemberName"),
        Attribute("M1", "Age"),
    ]
    assert result.rows == [Row([1, "Alice", 25])]


def test_evaluate_rename_preserves_original_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [Row(["Alice"])],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Rename(
        new_name="M1",
        expression=RelationReference("Member"),
        attribute_renames={"Name": "MemberName"},
    )

    evaluator.evaluate(expression)

    original = evaluator.evaluate(RelationReference("Member"))

    assert original.name == "Member"
    assert original.attributes == [
        Attribute("Member", "Name"),
    ]
    assert original.rows == [Row(["Alice"])]


def test_evaluate_rename_empty_relation():
    database = Database()

    members = Relation(
        "Member",
        [Attribute("Member", "Name")],
        [],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Rename(
        new_name="M1",
        expression=RelationReference("Member"),
    )

    result = evaluator.evaluate(expression)

    assert result.name == "M1"
    assert result.attributes == [
        Attribute("M1", "Name"),
    ]
    assert result.rows == []


def test_evaluate_self_join_with_rename():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Id"),
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [
            Row([1, "Alice", 25]),
            Row([2, "Bob", 25]),
            Row([3, "Charlie", 30]),
        ],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Join(
        left=Rename(
            new_name="M1",
            expression=RelationReference("Member"),
        ),
        condition=Comparison(
            left=AttributeReference("Age", "M1"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference("Age", "M2"),
        ),
        right=Rename(
            new_name="M2",
            expression=RelationReference("Member"),
        ),
    )

    result = evaluator.evaluate(expression)

    assert result.attributes == [
        Attribute("M1", "Id"),
        Attribute("M1", "Name"),
        Attribute("M1", "Age"),
        Attribute("M2", "Id"),
        Attribute("M2", "Name"),
        Attribute("M2", "Age"),
    ]

    assert result.rows == [
        Row([1, "Alice", 25, 1, "Alice", 25]),
        Row([1, "Alice", 25, 2, "Bob", 25]),
        Row([2, "Bob", 25, 1, "Alice", 25]),
        Row([2, "Bob", 25, 2, "Bob", 25]),
        Row([3, "Charlie", 30, 3, "Charlie", 30]),
    ]


def test_evaluate_self_join_with_rename_and_selection():
    database = Database()

    members = Relation(
        "Member",
        [
            Attribute("Member", "Id"),
            Attribute("Member", "Name"),
            Attribute("Member", "Age"),
        ],
        [
            Row([1, "Alice", 25]),
            Row([2, "Bob", 25]),
            Row([3, "Charlie", 30]),
        ],
    )

    database.add_relation(members)
    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference("Id", "M1"),
            operator=ComparisonOperator.LESS_THAN,
            right=AttributeReference("Id", "M2"),
        ),
        expression=Join(
            left=Rename(
                new_name="M1",
                expression=RelationReference("Member"),
            ),
            condition=Comparison(
                left=AttributeReference("Age", "M1"),
                operator=ComparisonOperator.EQUAL,
                right=AttributeReference("Age", "M2"),
            ),
            right=Rename(
                new_name="M2",
                expression=RelationReference("Member"),
            ),
        ),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row([1, "Alice", 25, 2, "Bob", 25]),
    ]


def test_selection_counter_counts_examined_tuples():
    database = Database()

    relation = Relation(
        "R",
        [
            Attribute("R", "a"),
            Attribute("R", "b"),
        ],
        [
            Row([0, 10]),
            Row([1, 20]),
            Row([2, 30]),
            Row([3, 40]),
            Row([4, 50]),
        ],
    )

    database.add_relation(relation)
    evaluator = Evaluator(database)

    expression = Select(
        condition=Comparison(
            left=AttributeReference(name="a"),
            operator=ComparisonOperator.GREATER_THAN,
            right=NumberLiteral(2),
        ),
        expression=RelationReference("R"),
    )

    result = evaluator.evaluate(expression)

    assert result.rows == [
        Row([3, 40]),
        Row([4, 50]),
    ]
    assert evaluator.selection_tuples_examined == 5


def test_join_counter_counts_tuple_pair_comparisons():
    database = Database()

    r = Relation(
        "R",
        [
            Attribute("R", "a"),
            Attribute("R", "b"),
        ],
        [
            Row([0, 0]),
            Row([1, 1]),
            Row([2, 2]),
            Row([3, 3]),
            Row([4, 4]),
        ],
    )

    s = Relation(
        "S",
        [
            Attribute("S", "b"),
            Attribute("S", "c"),
        ],
        [
            Row([0, 0]),
            Row([0, 1]),
            Row([1, 2]),
            Row([1, 3]),
            Row([2, 4]),
            Row([2, 5]),
            Row([3, 6]),
            Row([3, 7]),
            Row([4, 8]),
            Row([4, 9]),
        ],
    )

    database.add_relation(r)
    database.add_relation(s)
    evaluator = Evaluator(database)

    expression = Join(
        left=RelationReference("R"),
        condition=Comparison(
            left=AttributeReference(name="b", relation="R"),
            operator=ComparisonOperator.EQUAL,
            right=AttributeReference(name="b", relation="S"),
        ),
        right=RelationReference("S"),
    )

    result = evaluator.evaluate(expression)

    assert len(result.rows) == 10
    assert evaluator.join_comparisons == 50