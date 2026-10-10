import pytest

from src.engine.database import Database
from src.engine.query_processor import QueryProcessor
from src.engine.relation import Attribute, Row
from src.lexer.tokenizer import LexicalError
from src.parser.parser import ParseError


@pytest.fixture
def processor():
    return QueryProcessor(Database())


def test_create_relation_from_source(processor):
    result = processor.execute(
        """Member(Id, Name, Age) = {
1, Alice, 25
2, Bob, 30
3, Charlie, 22
}"""
    )

    assert result.name == "Member"
    assert result.attributes == [
        Attribute("Member", "Id"),
        Attribute("Member", "Name"),
        Attribute("Member", "Age"),
    ]
    assert result.rows == [
        Row([1, "Alice", 25]),
        Row([2, "Bob", 30]),
        Row([3, "Charlie", 22]),
    ]


def test_query_relation_created_from_source(processor):
    processor.execute(
        """Member(Id, Name, Age) = {
1, Alice, 25
2, Bob, 30
3, Charlie, 22
}"""
    )

    result = processor.execute(
        "project[Name](select[Age > 25](Member))"
    )

    assert result.attributes == [
        Attribute("Member", "Name"),
    ]
    assert result.rows == [
        Row(["Bob"]),
    ]


def test_query_with_union(processor):
    processor.execute(
        """A(Name) = {
Alice
Bob
}"""
    )

    processor.execute(
        """B(Name) = {
Bob
Charlie
}"""
    )

    result = processor.execute("A union B")

    assert result.rows == [
        Row(["Alice"]),
        Row(["Bob"]),
        Row(["Charlie"]),
    ]


def test_query_with_difference(processor):
    processor.execute(
        """A(Name) = {
Alice
Bob
Charlie
}"""
    )

    processor.execute(
        """B(Name) = {
Bob
}"""
    )

    result = processor.execute("A minus B")

    assert result.rows == [
        Row(["Alice"]),
        Row(["Charlie"]),
    ]


def test_query_with_rename_and_self_join(processor):
    processor.execute(
        """Member(Id, Name, Age) = {
1, Alice, 25
2, Bob, 25
3, Charlie, 30
}"""
    )

    result = processor.execute(
        "select[M1.Id < M2.Id]("
        "rename[M1](Member) "
        "join[M1.Age = M2.Age] "
        "rename[M2](Member)"
        ")"
    )

    assert result.rows == [
        Row([1, "Alice", 25, 2, "Bob", 25]),
    ]


def test_query_with_intersection(processor):
    processor.execute(
        """A(Name) = {
Alice
Bob
}"""
    )

    processor.execute(
        """B(Name) = {
Bob
Charlie
}"""
    )

    result = processor.execute("A intersect B")

    assert result.rows == [
        Row(["Bob"]),
    ]


def test_query_with_undefined_relation(processor):
    with pytest.raises((KeyError, NameError), match="UnknownRelation"):
        processor.execute("project[Name](UnknownRelation)")


def test_query_with_invalid_character(processor):
    with pytest.raises(LexicalError):
        processor.execute("project[Name](@Member)")


def test_projection_removes_duplicate_rows(processor):
    processor.execute(
        """Member(Id, Place) = {
1, Ottawa
2, Ottawa
3, Toronto
}"""
    )

    result = processor.execute("project[Place](Member)")

    assert result.attributes == [
        Attribute("Member", "Place"),
    ]
    assert len(result.rows) == 2
    assert {tuple(row.values) for row in result.rows} == {
        ("Ottawa",),
        ("Toronto",),
    }


def test_projection_preserves_requested_attribute_order(processor):
    processor.execute(
        """Member(Id, Name, Age) = {
1, Alice, 25
2, Bob, 30
}"""
    )

    result = processor.execute("project[Age, Name](Member)")

    assert result.attributes == [
        Attribute("Member", "Age"),
        Attribute("Member", "Name"),
    ]
    assert [row.values for row in result.rows] == [
        [25, "Alice"],
        [30, "Bob"],
    ]


def test_union_removes_duplicate_rows(processor):
    processor.execute(
        """A(Name) = {
Alice
Bob
}"""
    )

    processor.execute(
        """B(Name) = {
Bob
Charlie
}"""
    )

    result = processor.execute("A union B")

    assert len(result.rows) == 3
    assert {tuple(row.values) for row in result.rows} == {
        ("Alice",),
        ("Bob",),
        ("Charlie",),
    }


def test_union_rejects_different_attribute_counts(processor):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Name) = {
Alice
}"""
    )

    with pytest.raises(ValueError, match="different attribute counts"):
        processor.execute("A union B")


def test_union_rejects_different_attribute_names(processor):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Id, FullName) = {
2, Bob
}"""
    )

    with pytest.raises(ValueError, match="attribute names differ"):
        processor.execute("A union B")


def test_union_rejects_different_attribute_order(processor):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Name, Id) = {
Bob, 2
}"""
    )

    with pytest.raises(ValueError, match="attribute names differ"):
        processor.execute("A union B")


def test_union_rejects_incompatible_attribute_types(processor):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Id, Name) = {
Bob, Charlie
}"""
    )

    with pytest.raises(ValueError, match="incompatible attribute types"):
        processor.execute("A union B")


@pytest.mark.parametrize("operator", ["intersect", "minus"])
def test_other_set_operators_reject_incompatible_schemas(processor, operator):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Id, FullName) = {
2, Bob
}"""
    )

    with pytest.raises(ValueError, match="attribute names differ"):
        processor.execute(f"A {operator} B")


@pytest.mark.parametrize("operator", ["union", "intersect", "minus"])
def test_set_operators_preserve_left_input_schema(processor, operator):
    processor.execute(
        """A(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    processor.execute(
        """B(Id, Name) = {
2, Bob
3, Charlie
}"""
    )

    result = processor.execute(f"A {operator} B")

    assert result.attributes == [
        Attribute("A", "Id"),
        Attribute("A", "Name"),
    ]


def test_lexical_error_for_unterminated_string(processor):
    with pytest.raises(LexicalError, match="(?i)string"):
        processor.execute("select[Name='Bob](Member)")


def test_syntax_error_for_missing_parenthesis(processor):
    with pytest.raises(ParseError) as error:
        processor.execute("select[Age>30](Member")

    message = str(error.value).lower()

    assert (
        "expected" in message
        or "parenthesis" in message
        or ")" in message
    )


def test_name_error_for_unknown_relation(processor):
    with pytest.raises((NameError, KeyError), match="UnknownRelation"):
        processor.execute("UnknownRelation")


def test_name_error_for_unknown_attribute(processor):
    processor.execute(
        """Member(Id, Name) = {
1, Alice
}"""
    )

    with pytest.raises(NameError, match="Age"):
        processor.execute("project[Age](Member)")


def test_schema_error_for_incompatible_union(processor):
    processor.execute(
        """A(Id, Name) = {
1, Alice
}"""
    )

    processor.execute(
        """B(Id, FullName) = {
2, Bob
}"""
    )

    with pytest.raises(ValueError, match="union-compatible"):
        processor.execute("A union B")


def test_type_error_for_number_string_comparison(processor):
    processor.execute(
        """Member(Id, Age) = {
1, 30
}"""
    )

    with pytest.raises(TypeError, match="different types"):
        processor.execute("select[Age>'30'](Member)")


def test_required_case_24_duplicate_projection_attribute(processor):
    processor.execute(
        """Member(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    with pytest.raises(
        ValueError,
        match="Duplicate projection attribute: Name",
    ):
        processor.execute("project[Name, Name](Member)")


def test_required_case_11_minus_is_left_associative(processor):
    processor.execute(
        """A(Value) = {
1
2
}"""
    )

    processor.execute(
        """B(Value) = {
2
}"""
    )

    processor.execute(
        """C(Value) = {
2
}"""
    )

    result = processor.execute("A minus B minus C")

    assert result.rows == [
        Row([1]),
    ]

    alternative = processor.execute("A minus (B minus C)")

    assert alternative.rows == [
        Row([1]),
        Row([2]),
    ]

    assert result.rows != alternative.rows


def test_required_case_14_nested_operations_evaluation(processor):
    processor.execute(
        """Employees(EID, Name, Age, DID) = {
E1, Alice, 35, D1
E2, Bob, 40, D2
E3, Carol, 29, D1
E4, David, 45, D1
}"""
    )

    result = processor.execute(
        "project[Name](select[Age>30](select[DID='D1'](Employees)))"
    )

    assert result.rows == [
        Row(["Alice"]),
        Row(["David"]),
    ]


def test_required_case_18_attribute_to_attribute_comparison(processor):
    processor.execute(
        """R(A, B) = {
1, 1
2, 3
4, 4
5, 2
}"""
    )

    result = processor.execute("select[A=B](R)")

    assert [row.values for row in result.rows] == [
        [1, 1],
        [4, 4],
    ]


def test_required_case_19_join_preserves_qualified_attributes(processor):
    processor.execute(
        """Emp(EID, Name, DID) = {
E1, Alice, D1
E2, Bob, D2
E3, Carol, D1
}"""
    )

    processor.execute(
        """Dept(DID, DeptName) = {
D1, Engineering
D2, Finance
}"""
    )

    result = processor.execute(
        "Emp join[Emp.DID=Dept.DID] Dept"
    )

    assert [
        (attribute.relation, attribute.name)
        for attribute in result.attributes
    ] == [
        ("Emp", "EID"),
        ("Emp", "Name"),
        ("Emp", "DID"),
        ("Dept", "DID"),
        ("Dept", "DeptName"),
    ]

    assert [row.values for row in result.rows] == [
        ["E1", "Alice", "D1", "D1", "Engineering"],
        ["E2", "Bob", "D2", "D2", "Finance"],
        ["E3", "Carol", "D1", "D1", "Engineering"],
    ]


def test_required_case_20_self_join_with_rename(processor):
    processor.execute(
        """Emp(EID, Name, MgrID) = {
E1, Alice, E3
E2, Bob, E3
E3, Carol, E4
E4, David, E4
}"""
    )

    result = processor.execute(
        "Emp join[Emp.MgrID=E2.EID] rename[E2](Emp)"
    )

    assert [
        (attribute.relation, attribute.name)
        for attribute in result.attributes
    ] == [
        ("Emp", "EID"),
        ("Emp", "Name"),
        ("Emp", "MgrID"),
        ("E2", "EID"),
        ("E2", "Name"),
        ("E2", "MgrID"),
    ]

    assert [row.values for row in result.rows] == [
        ["E1", "Alice", "E3", "E3", "Carol", "E4"],
        ["E2", "Bob", "E3", "E3", "Carol", "E4"],
        ["E3", "Carol", "E4", "E4", "David", "E4"],
        ["E4", "David", "E4", "E4", "David", "E4"],
    ]


def test_times_rejects_qualified_attribute_collisions(processor):
    processor.execute(
        """R(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    with pytest.raises(
        ValueError,
        match=r"Attribute collision: R\.Id",
    ):
        processor.execute("R times R")


def test_times_allows_renamed_relation(processor):
    processor.execute(
        """R(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    result = processor.execute(
        "R times rename[R2](R)"
    )

    assert [
        (attribute.relation, attribute.name)
        for attribute in result.attributes
    ] == [
        ("R", "Id"),
        ("R", "Name"),
        ("R2", "Id"),
        ("R2", "Name"),
    ]

    assert [row.values for row in result.rows] == [
        [1, "Alice", 1, "Alice"],
        [1, "Alice", 2, "Bob"],
        [2, "Bob", 1, "Alice"],
        [2, "Bob", 2, "Bob"],
    ]


def test_join_rejects_qualified_attribute_collisions(processor):
    processor.execute(
        """R(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    with pytest.raises(
        ValueError,
        match=r"Attribute collision: R\.Id",
    ):
        processor.execute(
            "R join[R.Id=R.Id] R"
        )


def test_join_allows_renamed_relation(processor):
    processor.execute(
        """R(Id, Name) = {
1, Alice
2, Bob
}"""
    )

    result = processor.execute(
        "R join[R.Id=R2.Id] rename[R2](R)"
    )

    assert [
        (attribute.relation, attribute.name)
        for attribute in result.attributes
    ] == [
        ("R", "Id"),
        ("R", "Name"),
        ("R2", "Id"),
        ("R2", "Name"),
    ]

    assert [row.values for row in result.rows] == [
        [1, "Alice", 1, "Alice"],
        [2, "Bob", 2, "Bob"],
    ]