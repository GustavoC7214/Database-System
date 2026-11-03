"""Stage 1 tests for SQL semantic name resolution."""

from typing import cast

import pytest

from src.sql.catalog import SchemaCatalog
from src.sql.parser import parse_sql
from src.sql.semantic import NameResolver, SQLSemanticError
from src.storage.catalog import Catalog, TableMetadata


class FakeCatalog:
    """A predictable catalog for semantic tests."""

    def __init__(self) -> None:
        self.tables = {
            "Emp": TableMetadata(
                name="Emp",
                filename="Emp.db",
                schema=[
                    ("eid", "INT"),
                    ("name", "VARCHAR(40)"),
                    ("age", "INT"),
                    ("did", "INT"),
                    ("mgr", "INT"),
                    ("salary", "INT"),
                ],
            ),
            "Dept": TableMetadata(
                name="Dept",
                filename="Dept.db",
                schema=[
                    ("did", "INT"),
                    ("title", "VARCHAR(60)"),
                    ("budget", "INT"),
                ],
            ),
            "Office": TableMetadata(
                name="Office",
                filename="Office.db",
                schema=[
                    ("oid", "INT"),
                    ("did", "INT"),
                    ("city", "VARCHAR(40)"),
                ],
            ),
        }

    def get_table(self, name: str) -> TableMetadata:
        if name not in self.tables:
            raise ValueError(f"Table does not exist: {name}")
        return self.tables[name]

    def list_tables(self) -> list[str]:
        return list(self.tables)


@pytest.fixture
def resolver() -> NameResolver:
    catalog = SchemaCatalog(cast(Catalog, FakeCatalog()))
    return NameResolver(catalog)


def analyze(resolver: NameResolver, sql: str):
    statements = parse_sql(sql)
    assert len(statements) == 1
    return resolver.analyze(statements[0])


def test_single_table_column_resolution(resolver):
    result = analyze(resolver, "SELECT name, age FROM Emp;")
    assert [column.qualified_name for column in result.selected_columns] == [
        "Emp.name",
        "Emp.age",
    ]


def test_qualified_alias_resolution(resolver):
    result = analyze(resolver, "SELECT e.name FROM Emp AS e;")
    assert result.selected_columns[0].qualified_name == "e.name"


def test_implicit_alias_resolution(resolver):
    result = analyze(resolver, "SELECT e.name FROM Emp e;")
    assert result.selected_columns[0].qualified_name == "e.name"


def test_self_join_with_two_aliases(resolver):
    result = analyze(
        resolver,
        "SELECT e.name, m.name FROM Emp e JOIN Emp m ON e.mgr = m.eid;",
    )
    assert [entry.name for entry in result.scope] == ["e", "m"]
    assert [column.qualified_name for column in result.selected_columns] == [
        "e.name",
        "m.name",
    ]


def test_duplicate_table_alias_rejected(resolver):
    with pytest.raises(SQLSemanticError, match="duplicate table alias"):
        analyze(resolver, "SELECT * FROM Emp, Emp;")


def test_duplicate_explicit_alias_rejected(resolver):
    with pytest.raises(SQLSemanticError, match="duplicate table alias"):
        analyze(resolver, "SELECT * FROM Emp e, Dept e;")


def test_unqualified_ambiguous_column(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT did FROM Emp e JOIN Dept d ON e.did = d.did;",
        )

    assert error.value.category == "ambiguity"
    assert "e.did" in str(error.value)
    assert "d.did" in str(error.value)


def test_select_star_expansion(resolver):
    result = analyze(resolver, "SELECT * FROM Emp e, Dept d;")

    names = [column.qualified_name for column in result.selected_columns]

    assert names == [
        "e.eid",
        "e.name",
        "e.age",
        "e.did",
        "e.mgr",
        "e.salary",
        "d.did",
        "d.title",
        "d.budget",
    ]


def test_select_star_three_tables(resolver):
    result = analyze(
        resolver,
        "SELECT * FROM Emp e, Dept d, Office o;",
    )

    assert len(result.selected_columns) == 12
    assert "e.did" in [column.qualified_name for column in result.selected_columns]
    assert "d.did" in [column.qualified_name for column in result.selected_columns]
    assert "o.did" in [column.qualified_name for column in result.selected_columns]


def test_unknown_table(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(resolver, "SELECT id FROM Missing;")

    assert error.value.category == "name"
    assert "unknown table" in str(error.value)


def test_unknown_column(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(resolver, "SELECT missing FROM Emp;")

    assert error.value.category == "name"
    assert "unknown column" in str(error.value)


def test_unknown_qualifier(resolver):
    with pytest.raises(SQLSemanticError, match="unknown table or alias"):
        analyze(resolver, "SELECT x.name FROM Emp e;")


def test_unknown_qualified_column(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(resolver, "SELECT e.missing FROM Emp e;")


def test_alias_hides_original_table_name(resolver):
    with pytest.raises(SQLSemanticError, match="unknown table or alias"):
        analyze(resolver, "SELECT Emp.name FROM Emp e;")


def test_identifier_case_sensitive(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(resolver, "SELECT Name FROM Emp;")


def test_order_by_nonselected_column(resolver):
    result = analyze(
        resolver,
        "SELECT name FROM Emp ORDER BY age DESC;",
    )
    assert result.output[0].name == "name"


def test_order_by_output_alias(resolver):
    result = analyze(
        resolver,
        "SELECT name AS employee FROM Emp ORDER BY employee;",
    )
    assert result.output[0].name == "employee"


def test_derived_table_output(resolver):
    result = analyze(
        resolver,
        "SELECT t.did, t.n FROM "
        "(SELECT did, COUNT(*) AS n FROM Emp GROUP BY did) AS t;",
    )

    assert result.scope[0].name == "t"
    assert [column.qualified_name for column in result.selected_columns] == [
        "t.did",
        "t.n",
    ]


def test_derived_table_join(resolver):
    result = analyze(
        resolver,
        "SELECT t.did, d.title FROM "
        "(SELECT did, COUNT(*) AS n FROM Emp GROUP BY did) AS t "
        "JOIN Dept d ON t.did = d.did;",
    )
    assert [entry.name for entry in result.scope] == ["t", "d"]


def test_derived_table_hides_internal_columns(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(
            resolver,
            "SELECT t.age FROM (SELECT did FROM Emp) AS t;",
        )


def test_derived_table_duplicate_output_names(resolver):
    with pytest.raises(SQLSemanticError, match="duplicate output names"):
        analyze(
            resolver,
            "SELECT t.did FROM (SELECT e.did, d.did FROM Emp e, Dept d) AS t;",
        )


def test_unknown_column_in_where(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(
            resolver,
            "SELECT name FROM Emp WHERE missing = 10;",
        )


def test_unknown_column_in_join_condition(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(
            resolver,
            "SELECT e.name FROM Emp e JOIN Dept d ON e.missing = d.did;",
        )


def test_unknown_column_in_group_by(resolver):
    with pytest.raises(SQLSemanticError, match="unknown column"):
        analyze(
            resolver,
            "SELECT COUNT(*) FROM Emp GROUP BY missing;",
        )


def test_semantic_error_source_location(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT\n  missing\nFROM Emp;",
        )

    assert error.value.line == 2
    assert error.value.column == 3
    assert "at line 2, column 3" in str(error.value)


# ------------------------------------------------------------
# Stage 2: Type checking and aggregate validation
# ------------------------------------------------------------


def test_integer_comparison_valid(resolver):
    result = analyze(
        resolver,
        "SELECT name FROM Emp WHERE age > 30;",
    )
    assert result.output[0].name == "name"


def test_string_comparison_valid(resolver):
    result = analyze(
        resolver,
        "SELECT name FROM Emp WHERE name = 'Alice';",
    )
    assert result.output[0].data_type == "VARCHAR(40)"


def test_integer_string_comparison_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name FROM Emp WHERE age > '30';",
        )
    assert error.value.category == "type"


def test_integer_string_equality_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name FROM Emp WHERE age = '30';",
        )
    assert error.value.category == "type"


def test_incompatible_join_types_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT e.name FROM Emp e JOIN Dept d ON e.name = d.did;",
        )
    assert error.value.category == "type"


def test_compatible_varchar_lengths(resolver):
    result = analyze(
        resolver,
        "SELECT e.name FROM Emp e JOIN Dept d ON e.name = d.title;",
    )
    assert result.output[0].name == "name"


@pytest.mark.parametrize(
    "function",
    ["SUM", "AVG"],
)
def test_numeric_aggregates_valid(resolver, function):
    result = analyze(
        resolver,
        f"SELECT {function}(salary) AS total FROM Emp;",
    )
    assert result.output[0].data_type == "INT"


@pytest.mark.parametrize(
    "function",
    ["SUM", "AVG"],
)
def test_numeric_aggregates_reject_varchar(resolver, function):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            f"SELECT {function}(name) FROM Emp;",
        )
    assert error.value.category == "aggregate"


def test_count_star_valid(resolver):
    result = analyze(
        resolver,
        "SELECT COUNT(*) AS n FROM Emp;",
    )
    assert result.output[0].name == "n"
    assert result.output[0].data_type == "INT"


def test_count_string_column_valid(resolver):
    result = analyze(
        resolver,
        "SELECT COUNT(name) FROM Emp;",
    )
    assert result.output[0].data_type == "INT"


@pytest.mark.parametrize(
    "function",
    ["MIN", "MAX"],
)
def test_min_max_varchar_valid(resolver, function):
    result = analyze(
        resolver,
        f"SELECT {function}(name) FROM Emp;",
    )
    assert result.output[0].data_type == "VARCHAR(40)"


def test_group_by_column_and_aggregate_valid(resolver):
    result = analyze(
        resolver,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did;",
    )
    assert [column.name for column in result.output] == [
        "did",
        "n",
    ]


def test_non_grouped_select_column_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name, COUNT(*) FROM Emp GROUP BY did;",
        )
    assert error.value.category == "aggregate"


def test_non_grouped_column_without_aggregate_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name FROM Emp GROUP BY did;",
        )
    assert error.value.category == "aggregate"


def test_non_aggregated_column_with_count_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name, COUNT(*) FROM Emp;",
        )
    assert error.value.category == "aggregate"


def test_aggregate_in_where_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT name FROM Emp WHERE COUNT(*) > 2;",
        )
    assert error.value.category == "aggregate"


def test_aggregate_in_join_condition_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT e.name FROM Emp e JOIN Dept d ON COUNT(*) > d.did;",
        )
    assert error.value.category == "aggregate"


def test_having_aggregate_valid(resolver):
    result = analyze(
        resolver,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did HAVING COUNT(*) > 5;",
    )
    assert result.output[1].name == "n"


def test_having_output_alias_valid(resolver):
    result = analyze(
        resolver,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did HAVING n > 5;",
    )
    assert result.output[1].data_type == "INT"


def test_having_non_grouped_column_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT did, COUNT(*) FROM Emp GROUP BY did HAVING age > 25;",
        )
    assert error.value.category == "aggregate"


def test_having_without_group_by_rejected():
    from src.sql.parser import SQLSyntaxError

    with pytest.raises(SQLSyntaxError) as error:
        parse_sql("SELECT name FROM Emp HAVING age > 20;")

    assert "error: syntax:" in str(error.value)


def test_order_by_non_grouped_column_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT did, COUNT(*) FROM Emp GROUP BY did ORDER BY age;",
        )
    assert error.value.category == "aggregate"


def test_order_by_aggregate_alias_valid(resolver):
    result = analyze(
        resolver,
        "SELECT did, COUNT(*) AS n FROM Emp GROUP BY did ORDER BY n DESC;",
    )
    assert result.output[1].name == "n"


def test_union_compatible_types(resolver):
    result = analyze(
        resolver,
        "SELECT eid FROM Emp UNION SELECT did FROM Dept;",
    )
    assert len(result.output) == 1
    assert result.output[0].data_type == "INT"


def test_union_all_compatible_types(resolver):
    result = analyze(
        resolver,
        "SELECT name FROM Emp UNION ALL SELECT title FROM Dept;",
    )
    assert len(result.output) == 1


def test_union_incompatible_types_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT eid FROM Emp UNION SELECT title FROM Dept;",
        )
    assert error.value.category == "type"


def test_union_column_count_mismatch_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT eid, name FROM Emp UNION SELECT did FROM Dept;",
        )
    assert error.value.category == "schema"


@pytest.mark.parametrize(
    "operator",
    ["INTERSECT", "EXCEPT"],
)
def test_other_set_operations_type_check(resolver, operator):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            f"SELECT eid FROM Emp {operator} SELECT title FROM Dept;",
        )
    assert error.value.category == "type"


def test_set_operation_preserves_left_output_names(resolver):
    result = analyze(
        resolver,
        "SELECT eid AS identifier FROM Emp "
        "UNION SELECT did AS department_id FROM Dept;",
    )
    assert result.output[0].name == "identifier"


def test_derived_table_aggregate_type(resolver):
    result = analyze(
        resolver,
        "SELECT t.n FROM (SELECT COUNT(*) AS n FROM Emp) AS t;",
    )
    assert result.output[0].data_type == "INT"


def test_derived_table_invalid_aggregate_rejected(resolver):
    with pytest.raises(SQLSemanticError) as error:
        analyze(
            resolver,
            "SELECT t.n FROM (SELECT SUM(name) AS n FROM Emp) AS t;",
        )
    assert error.value.category == "aggregate"
