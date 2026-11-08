import pytest

from src.storage.schema import parse_schema


def test_parse_single_int_column():
    assert parse_schema("id:INT") == [("id", "INT")]


def test_parse_single_varchar_column():
    assert parse_schema("name:VARCHAR(20)") == [("name", "VARCHAR(20)")]


def test_parse_multiple_columns():
    schema = parse_schema("a:INT,b:VARCHAR(20),c:INT")

    assert schema == [
        ("a", "INT"),
        ("b", "VARCHAR(20)"),
        ("c", "INT"),
    ]


def test_parse_schema_normalizes_types():
    assert parse_schema("id:int,name:varchar(20)") == [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
    ]


def test_parse_schema_allows_whitespace():
    assert parse_schema(" id : INT , name : VARCHAR(20) ") == [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
    ]


def test_parse_schema_varchar_boundaries():
    assert parse_schema("a:VARCHAR(1),b:VARCHAR(255)") == [
        ("a", "VARCHAR(1)"),
        ("b", "VARCHAR(255)"),
    ]


def test_parse_schema_rejects_empty_input():
    with pytest.raises(ValueError, match="Schema cannot be empty"):
        parse_schema("")

    with pytest.raises(ValueError, match="Schema cannot be empty"):
        parse_schema("   ")


def test_parse_schema_rejects_missing_type():
    with pytest.raises(ValueError, match="Invalid column definition"):
        parse_schema("id:")


def test_parse_schema_rejects_missing_separator():
    with pytest.raises(ValueError, match="Invalid column definition"):
        parse_schema("id INT")


def test_parse_schema_rejects_invalid_column_name():
    with pytest.raises(ValueError, match="Invalid column name"):
        parse_schema("1name:INT")


def test_parse_schema_rejects_duplicate_columns():
    with pytest.raises(ValueError, match="Duplicate column name"):
        parse_schema("id:INT,id:VARCHAR(20)")


def test_parse_schema_rejects_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported column type"):
        parse_schema("price:FLOAT")


def test_parse_schema_rejects_varchar_length_out_of_range():
    with pytest.raises(ValueError, match="between 1 and 255"):
        parse_schema("name:VARCHAR(0)")

    with pytest.raises(ValueError, match="between 1 and 255"):
        parse_schema("name:VARCHAR(256)")


def test_parse_schema_rejects_trailing_comma():
    with pytest.raises(ValueError, match="Invalid column definition"):
        parse_schema("id:INT,")
