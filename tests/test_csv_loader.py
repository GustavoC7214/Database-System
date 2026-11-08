import pytest

from src.storage.catalog import Catalog
from src.storage.csv_loader import convert_csv_row, load_csv
from src.storage.heap_file import HeapFile
from src.storage.record_codec import decode_record


def test_convert_csv_row():
    schema = [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
        ("age", "INT"),
    ]

    result = convert_csv_row(["1", "Alice", "20"], schema, 1)

    assert result == (1, "Alice", 20)


def test_convert_negative_integer():
    schema = [("value", "INT")]

    assert convert_csv_row(["-7"], schema, 1) == (-7,)


def test_convert_empty_varchar():
    schema = [("name", "VARCHAR(20)")]

    assert convert_csv_row([""], schema, 1) == ("",)


def test_convert_varchar_with_comma():
    schema = [("name", "VARCHAR(20)")]

    assert convert_csv_row(["Smith, John"], schema, 1) == ("Smith, John",)


def test_convert_csv_row_rejects_missing_columns():
    schema = [("id", "INT"), ("name", "VARCHAR(20)")]

    with pytest.raises(ValueError, match="CSV row 3: expected 2 columns"):
        convert_csv_row(["1"], schema, 3)


def test_convert_csv_row_rejects_extra_columns():
    schema = [("id", "INT")]

    with pytest.raises(ValueError, match="CSV row 2: expected 1 columns"):
        convert_csv_row(["1", "Alice"], schema, 2)


def test_convert_csv_row_rejects_invalid_integer():
    schema = [("age", "INT")]

    with pytest.raises(
        ValueError,
        match=r"CSV row 4, column 1 \(age\): invalid INT",
    ):
        convert_csv_row(["twenty"], schema, 4)


def test_convert_csv_row_rejects_integer_overflow():
    schema = [("id", "INT")]

    with pytest.raises(ValueError, match="outside signed 32-bit range"):
        convert_csv_row([str(2**31)], schema, 1)


def test_convert_csv_row_rejects_oversized_varchar():
    schema = [("name", "VARCHAR(3)")]

    with pytest.raises(ValueError, match="maximum is 3"):
        convert_csv_row(["Alice"], schema, 5)


def test_convert_csv_row_counts_utf8_bytes():
    schema = [("name", "VARCHAR(1)")]

    with pytest.raises(ValueError, match="2 bytes"):
        convert_csv_row(["é"], schema, 1)


def test_convert_csv_row_rejects_unsupported_type():
    schema = [("price", "FLOAT")]

    with pytest.raises(ValueError, match="unsupported type FLOAT"):
        convert_csv_row(["3.14"], schema, 1)


def test_load_csv_basic(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Students", "id:INT,name:VARCHAR(50),age:INT")

    csv_path = tmp_path / "students.csv"
    csv_path.write_text("1,Alice,20\n2,Bob,21\n", encoding="utf-8")

    count = load_csv(tmp_path, "Students", csv_path)

    assert count == 2

    metadata = Catalog(tmp_path).get_table("Students")
    assert metadata.tuple_count == 2

    heap = HeapFile(tmp_path / metadata.filename)
    rows = [decode_record(data, metadata.schema) for _, data in heap.scan()]

    assert rows == [(1, "Alice", 20), (2, "Bob", 21)]


def test_load_csv_handles_quoted_commas_and_unicode(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("People", "id:INT,name:VARCHAR(50)")

    csv_path = tmp_path / "people.csv"
    csv_path.write_text(
        '1,"Smith, John"\n2,"Café"\n',
        encoding="utf-8",
    )

    assert load_csv(tmp_path, "People", csv_path) == 2

    metadata = Catalog(tmp_path).get_table("People")
    heap = HeapFile(tmp_path / metadata.filename)

    rows = [decode_record(data, metadata.schema) for _, data in heap.scan()]

    assert rows == [(1, "Smith, John"), (2, "Café")]


def test_load_csv_updates_page_count(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Numbers", "value:INT")

    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text(
        "".join(f"{number}\n" for number in range(1000)),
        encoding="utf-8",
    )

    assert load_csv(tmp_path, "Numbers", csv_path) == 1000

    metadata = Catalog(tmp_path).get_table("Numbers")
    heap = HeapFile(tmp_path / metadata.filename)

    assert metadata.page_count == heap.page_count
    assert metadata.page_count > 2
    assert metadata.tuple_count == 1000


def test_load_csv_multiple_times(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Numbers", "value:INT")

    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text("1\n2\n", encoding="utf-8")

    assert load_csv(tmp_path, "Numbers", csv_path) == 2
    assert load_csv(tmp_path, "Numbers", csv_path) == 2

    metadata = Catalog(tmp_path).get_table("Numbers")

    assert metadata.tuple_count == 4


def test_load_csv_partial_failure_preserves_inserted_rows(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Numbers", "value:INT")

    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text("1\n2\ninvalid\n4\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CSV row 3"):
        load_csv(tmp_path, "Numbers", csv_path)

    metadata = Catalog(tmp_path).get_table("Numbers")
    assert metadata.tuple_count == 2

    heap = HeapFile(tmp_path / metadata.filename)
    rows = [decode_record(data, metadata.schema) for _, data in heap.scan()]

    assert rows == [(1,), (2,)]


def test_load_csv_missing_table(tmp_path):
    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text("1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Table does not exist"):
        load_csv(tmp_path, "Missing", csv_path)


def test_load_csv_error_identifies_table_row_and_column(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Students", "id:INT,age:INT")

    csv_path = tmp_path / "students.csv"
    csv_path.write_text(
        "1,20\n2,invalid\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"Table Students: CSV row 2, column 2 \(age\)",
    ):
        load_csv(tmp_path, "Students", csv_path)

    metadata = Catalog(tmp_path).get_table("Students")
    assert metadata.tuple_count == 1


def test_load_csv_reports_malformed_quoting(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("People", "id:INT,name:VARCHAR(50)")

    csv_path = tmp_path / "people.csv"
    csv_path.write_text(
        '1,Alice\n2,"Unclosed name\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"Table People.*line 2.*column",
    ):
        load_csv(tmp_path, "People", csv_path)

    metadata = Catalog(tmp_path).get_table("People")
    assert metadata.tuple_count == 1


def test_load_csv_handles_multiline_quoted_fields(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Notes", "id:INT,text:VARCHAR(100)")

    csv_path = tmp_path / "notes.csv"
    csv_path.write_text(
        '1,"First line\nSecond line"\n2,"Normal text"\n',
        encoding="utf-8",
    )

    assert load_csv(tmp_path, "Notes", csv_path) == 2

    metadata = Catalog(tmp_path).get_table("Notes")
    heap = HeapFile(tmp_path / metadata.filename)

    rows = [decode_record(data, metadata.schema) for _, data in heap.scan()]

    assert rows == [
        (1, "First line\nSecond line"),
        (2, "Normal text"),
    ]
    assert metadata.tuple_count == 2
