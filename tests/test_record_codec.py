import pytest

from src.storage.record_codec import (
    decode_int,
    decode_record,
    decode_varchar,
    encode_int,
    encode_record,
    encode_varchar,
)


def test_encode_positive_integer():
    assert encode_int(42) == b"\x2a\x00\x00\x00"


def test_encode_negative_integer():
    assert encode_int(-1) == b"\xff\xff\xff\xff"


def test_encode_zero():
    assert encode_int(0) == b"\x00\x00\x00\x00"


def test_decode_positive_integer():
    assert decode_int(b"\x2a\x00\x00\x00") == 42


def test_decode_negative_integer():
    assert decode_int(b"\xff\xff\xff\xff") == -1


def test_int_round_trip():
    values = [0, 1, -1, 42, -42, -(2**31), 2**31 - 1]

    for value in values:
        assert decode_int(encode_int(value)) == value


def test_encode_int_rejects_out_of_range():
    with pytest.raises(ValueError, match="32-bit"):
        encode_int(2**31)

    with pytest.raises(ValueError, match="32-bit"):
        encode_int(-(2**31) - 1)


def test_encode_int_rejects_invalid_types():
    invalid_values: list[object] = ["42", True]

    for value in invalid_values:
        with pytest.raises(TypeError):
            encode_int(value)  # type: ignore[arg-type]


def test_decode_int_rejects_invalid_length():
    with pytest.raises(ValueError, match="exactly 4 bytes"):
        decode_int(b"\x01\x02")


def test_encode_varchar():
    assert encode_varchar("bob", 20) == b"\x03\x00bob"


def test_encode_empty_varchar():
    assert encode_varchar("", 20) == b"\x00\x00"


def test_decode_varchar():
    assert decode_varchar(b"\x03\x00bob", 20) == "bob"


def test_varchar_round_trip():
    values = ["", "Alice", "hello world", "café", "你好"]

    for value in values:
        assert decode_varchar(encode_varchar(value, 255), 255) == value


def test_varchar_length_counts_utf8_bytes():
    # "é" is 2 bytes in UTF-8, despite being one character.
    assert encode_varchar("é", 2) == b"\x02\x00\xc3\xa9"

    with pytest.raises(ValueError, match="maximum"):
        encode_varchar("é", 1)


def test_varchar_rejects_oversized_value():
    with pytest.raises(ValueError, match="maximum"):
        encode_varchar("A" * 21, 20)


def test_varchar_rejects_invalid_schema_length():
    with pytest.raises(ValueError, match="between 1 and 255"):
        encode_varchar("hello", 0)

    with pytest.raises(ValueError, match="between 1 and 255"):
        encode_varchar("hello", 256)


def test_varchar_rejects_invalid_value_type():
    value: object = 123

    with pytest.raises(TypeError):
        encode_varchar(value, 20)  # type: ignore[arg-type]


def test_decode_varchar_rejects_missing_prefix():
    with pytest.raises(ValueError, match="length prefix"):
        decode_varchar(b"\x03", 20)


def test_decode_varchar_rejects_truncated_data():
    with pytest.raises(ValueError, match="does not match prefix"):
        decode_varchar(b"\x05\x00bob", 20)


def test_decode_varchar_rejects_excess_data():
    with pytest.raises(ValueError, match="does not match prefix"):
        decode_varchar(b"\x03\x00bobby", 20)


def test_decode_varchar_rejects_schema_overflow():
    with pytest.raises(ValueError, match="exceeds schema limit"):
        decode_varchar(b"\x03\x00bob", 2)


def test_decode_varchar_rejects_invalid_utf8():
    with pytest.raises(UnicodeDecodeError):
        decode_varchar(b"\x01\x00\xff", 20)


def test_encode_complete_record():
    schema = [
        ("a", "INT"),
        ("b", "VARCHAR(20)"),
        ("c", "INT"),
    ]

    result = encode_record((42, "bob", 7), schema)

    assert result == (b"\x2a\x00\x00\x00\x03\x00bob\x07\x00\x00\x00")
    assert len(result) == 13


def test_encode_record_with_negative_integer():
    schema = [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
    ]

    assert encode_record((-1, "Alice"), schema) == (b"\xff\xff\xff\xff\x05\x00Alice")


def test_encode_record_with_empty_string():
    schema = [("name", "VARCHAR(10)")]

    assert encode_record(("",), schema) == b"\x00\x00"


def test_encode_record_rejects_wrong_column_count():
    schema = [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
    ]

    with pytest.raises(ValueError, match="Expected 2 values"):
        encode_record((42,), schema)


def test_encode_record_rejects_wrong_column_type():
    schema = [("age", "INT")]

    value: object = "twenty"

    with pytest.raises(TypeError, match="Column age requires INT"):
        encode_record((value,), schema)  # type: ignore[arg-type]


def test_encode_record_rejects_unsupported_type():
    schema = [("price", "FLOAT")]

    with pytest.raises(ValueError, match="Unsupported type"):
        encode_record((42,), schema)


def test_encode_record_rejects_invalid_varchar_type():
    schema = [("name", "VARCHAR(abc)")]

    with pytest.raises(ValueError, match="Invalid type"):
        encode_record(("Alice",), schema)


def test_decode_complete_record():
    schema = [
        ("a", "INT"),
        ("b", "VARCHAR(20)"),
        ("c", "INT"),
    ]

    data = b"\x2a\x00\x00\x00\x03\x00bob\x07\x00\x00\x00"

    assert decode_record(data, schema) == (42, "bob", 7)


def test_record_round_trip():
    schema = [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
        ("age", "INT"),
    ]

    records = [
        (1, "Alice", 20),
        (2, "Bob", 25),
        (-1, "", 0),
        (42, "café", -5),
    ]

    for record in records:
        encoded = encode_record(record, schema)
        assert decode_record(encoded, schema) == record


def test_decode_record_rejects_truncated_int():
    schema = [("id", "INT")]

    with pytest.raises(ValueError, match="Insufficient data"):
        decode_record(b"\x2a\x00", schema)


def test_decode_record_rejects_missing_varchar_length():
    schema = [("name", "VARCHAR(20)")]

    with pytest.raises(ValueError, match="Missing VARCHAR length"):
        decode_record(b"\x03", schema)


def test_decode_record_rejects_truncated_varchar():
    schema = [("name", "VARCHAR(20)")]

    with pytest.raises(ValueError, match="Truncated VARCHAR"):
        decode_record(b"\x05\x00bob", schema)


def test_decode_record_rejects_trailing_bytes():
    schema = [("id", "INT")]

    with pytest.raises(ValueError, match="unexpected trailing bytes"):
        decode_record(b"\x2a\x00\x00\x00\xff", schema)


def test_decode_record_rejects_unsupported_type():
    schema = [("price", "FLOAT")]

    with pytest.raises(ValueError, match="Unsupported type"):
        decode_record(b"\x00\x00\x00\x00", schema)


def test_decode_record_rejects_invalid_varchar_schema():
    schema = [("name", "VARCHAR(abc)")]

    with pytest.raises(ValueError, match="Invalid type"):
        decode_record(b"\x03\x00bob", schema)


def test_decode_record_rejects_varchar_schema_overflow():
    schema = [("name", "VARCHAR(256)")]

    with pytest.raises(ValueError, match="Invalid VARCHAR length"):
        decode_record(b"\x03\x00bob", schema)


def test_decode_record_rejects_varchar_length_overflow():
    schema = [("name", "VARCHAR(2)")]

    with pytest.raises(ValueError, match="exceeds schema limit"):
        decode_record(b"\x03\x00bob", schema)
