"""Tests for the Module 3 recursive-descent SQL parser."""

import pytest

from src.sql import ast
from src.sql.parser import SQLSyntaxError, parse_sql


def single(sql: str) -> ast.Statement:
    statements = parse_sql(sql)
    assert len(statements) == 1
    return statements[0]


def test_create_table():
    result = single("CREATE TABLE Emp (id INT, name VARCHAR(40));")
    assert isinstance(result, ast.CreateTable)
    assert result.name == "Emp"
    assert result.columns[0] == ast.ColumnDefinition("id", "INT")
    assert result.columns[1] == ast.ColumnDefinition("name", "VARCHAR", 40)


def test_insert():
    result = single("INSERT INTO Emp VALUES (1, 'O''Brien', -5);")
    assert isinstance(result, ast.Insert)
    assert [value.value for value in result.values] == [1, "O'Brien", -5]


def test_simple_select():
    result = single("SELECT name, age FROM Emp;")
    assert isinstance(result, ast.Select)
    assert result.columns is not None
    assert len(result.columns) == 2
    assert result.source == ast.Table("Emp")


def test_select_star():
    result = single("SELECT * FROM Emp;")
    assert isinstance(result, ast.Select)
    assert result.columns is None


def test_distinct():
    result = single("SELECT DISTINCT did FROM Emp;")
    assert isinstance(result, ast.Select)
    assert result.distinct is True


def test_qualified_columns_and_aliases():
    result = single("SELECT e.name AS employee FROM Emp AS e;")
    assert isinstance(result, ast.Select)
    assert result.source == ast.Table("Emp", "e")
    assert result.columns == (ast.SelectItem(ast.Column("name", "e"), "employee"),)


def test_boolean_precedence():
    result = single("SELECT * FROM Emp WHERE a = 1 OR b = 2 AND NOT c = 3;")
    assert isinstance(result, ast.Select)
    assert isinstance(result.where, ast.Logical)
    assert result.where.operator == "OR"
    assert isinstance(result.where.right, ast.Logical)
    assert result.where.right.operator == "AND"
    assert isinstance(result.where.right.right, ast.Negation)


def test_parenthesized_conditions():
    result = single("SELECT * FROM Emp WHERE (a = 1 OR b = 2) AND c = 3;")
    assert isinstance(result, ast.Select)
    assert isinstance(result.where, ast.Logical)
    assert result.where.operator == "AND"
    assert isinstance(result.where.left, ast.Logical)
    assert result.where.left.operator == "OR"


def test_explicit_join():
    result = single("SELECT e.name FROM Emp e JOIN Dept d ON e.did = d.did;")
    assert isinstance(result, ast.Select)
    assert result.extensions[0].kind == "JOIN"
    assert result.extensions[0].table == ast.Table("Dept", "d")
    assert isinstance(result.extensions[0].condition, ast.Comparison)


def test_comma_join():
    result = single("SELECT * FROM Emp e, Dept d;")
    assert isinstance(result, ast.Select)
    assert result.extensions[0].kind == "CROSS"
    assert result.extensions[0].condition is None


def test_mixed_join_order():
    result = single("SELECT * FROM A a, B b JOIN C c ON b.id = c.id, D d;")
    assert isinstance(result, ast.Select)
    assert [item.kind for item in result.extensions] == [
        "CROSS",
        "JOIN",
        "CROSS",
    ]


def test_group_by_having():
    result = single(
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did HAVING COUNT(*) > 2;"
    )
    assert isinstance(result, ast.Select)
    assert result.group_by == (ast.Column("did"),)
    assert isinstance(result.having, ast.Comparison)
    assert isinstance(result.having.left, ast.Aggregate)


def test_order_by_and_limit():
    result = single("SELECT name FROM Emp ORDER BY age DESC, name LIMIT 10;")
    assert isinstance(result, ast.Select)
    assert result.order_by[0] == ast.SortItem(ast.Column("age"), "DESC")
    assert result.order_by[1].direction == "ASC"
    assert result.limit == 10


def test_derived_table():
    result = single("SELECT t.did FROM (SELECT did FROM Emp) AS t;")
    assert isinstance(result, ast.Select)
    assert isinstance(result.source, ast.DerivedTable)
    assert result.source.alias == "t"
    assert isinstance(result.source.query, ast.Select)


def test_set_operations_left_associative():
    result = single(
        "SELECT id FROM A UNION SELECT id FROM B INTERSECT SELECT id FROM C;"
    )
    assert isinstance(result, ast.SetOperation)
    assert result.operator == "INTERSECT"
    assert isinstance(result.left, ast.SetOperation)
    assert result.left.operator == "UNION"


def test_union_all():
    result = single("SELECT id FROM A UNION ALL SELECT id FROM B;")
    assert isinstance(result, ast.SetOperation)
    assert result.operator == "UNION ALL"


def test_parenthesized_set_operations():
    result = single(
        "SELECT id FROM A UNION (SELECT id FROM B EXCEPT SELECT id FROM C);"
    )
    assert isinstance(result, ast.SetOperation)
    assert isinstance(result.right, ast.SetOperation)
    assert result.right.operator == "EXCEPT"


def test_multiple_statements():
    result = parse_sql(
        "CREATE TABLE T (id INT);INSERT INTO T VALUES (1);SELECT id FROM T;"
    )
    assert len(result) == 3


def test_empty_input():
    assert parse_sql("") == ()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT FROM Emp;",
        "SELECT name Emp;",
        "CREATE TABLE T ();",
        "INSERT INTO T VALUES ();",
        "SELECT * FROM Emp WHERE age >;",
        "SELECT * FROM Emp ORDER BY;",
        "SELECT * FROM Emp LIMIT -1;",
        "SELECT * FROM (SELECT id FROM Emp);",
        "SELECT * FROM Emp JOIN Dept;",
        "SELECT * FROM Emp SELECT * FROM Dept;",
    ],
)
def test_invalid_syntax(sql):
    with pytest.raises(SQLSyntaxError, match="error: syntax:"):
        parse_sql(sql)


def test_syntax_error_location():
    with pytest.raises(SQLSyntaxError) as error:
        parse_sql("SELECT name\nFROM;")

    assert error.value.line == 2
    assert error.value.column == 5


def test_count_star():
    result = single("SELECT COUNT(*) AS total FROM Emp;")
    assert isinstance(result, ast.Select)
    assert result.columns is not None
    assert result.columns[0].expression == ast.Aggregate("COUNT", None)


def test_sum_star_rejected():
    with pytest.raises(SQLSyntaxError, match="only COUNT supports"):
        parse_sql("SELECT SUM(*) FROM Emp;")


def test_varchar_requires_positive_length():
    with pytest.raises(SQLSyntaxError, match="positive integer"):
        parse_sql("CREATE TABLE T (name VARCHAR(0));")


def test_limit_zero():
    result = single("SELECT * FROM Emp LIMIT 0;")
    assert isinstance(result, ast.Select)
    assert result.limit == 0
