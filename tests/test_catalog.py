import pytest

from src.storage.catalog import (
    Catalog,
    TableMetadata,
    decode_metadata,
    encode_metadata,
)


def test_encode_metadata_returns_bytes():
    metadata = TableMetadata(
        name="R",
        filename="R.db",
        schema=[("a", "INT")],
    )

    result = encode_metadata(metadata)

    assert isinstance(result, bytes)


def test_metadata_round_trip():
    metadata = TableMetadata(
        name="R",
        filename="R.db",
        schema=[
            ("a", "INT"),
            ("b", "VARCHAR(20)"),
            ("c", "INT"),
        ],
        page_count=3,
        tuple_count=250,
    )

    encoded = encode_metadata(metadata)
    decoded = decode_metadata(encoded)

    assert decoded == metadata


def test_metadata_defaults():
    metadata = TableMetadata(
        name="Students",
        filename="Students.db",
        schema=[
            ("id", "INT"),
            ("name", "VARCHAR(50)"),
        ],
    )

    decoded = decode_metadata(encode_metadata(metadata))

    assert decoded.page_count == 0
    assert decoded.tuple_count == 0


def test_metadata_preserves_unicode():
    metadata = TableMetadata(
        name="Café",
        filename="Café.db",
        schema=[("description", "VARCHAR(100)")],
    )

    decoded = decode_metadata(encode_metadata(metadata))

    assert decoded.name == "Café"
    assert decoded.filename == "Café.db"


def test_metadata_encoding_is_deterministic():
    metadata = TableMetadata(
        name="R",
        filename="R.db",
        schema=[("id", "INT")],
    )

    first = encode_metadata(metadata)
    second = encode_metadata(metadata)

    assert first == second


def test_catalog_creates_database_file(tmp_path):
    catalog = Catalog(tmp_path)

    assert (tmp_path / "catalog.db").exists()
    assert catalog.heap.page_count == 1


def test_catalog_creates_missing_directory(tmp_path):
    db_dir = tmp_path / "my_database"

    Catalog(db_dir)

    assert db_dir.is_dir()
    assert (db_dir / "catalog.db").exists()


def test_catalog_lists_empty_database(tmp_path):
    catalog = Catalog(tmp_path)

    assert catalog.list_tables() == []


def test_catalog_rejects_unknown_table(tmp_path):
    catalog = Catalog(tmp_path)

    with pytest.raises(ValueError, match="Table does not exist: R"):
        catalog.get_table("R")


def test_create_table_creates_file(tmp_path):
    catalog = Catalog(tmp_path)

    metadata = catalog.create_table(
        "R",
        "a:INT,b:VARCHAR(20),c:INT",
    )

    assert (tmp_path / "R.db").exists()
    assert metadata.name == "R"
    assert metadata.filename == "R.db"
    assert metadata.page_count == 1
    assert metadata.tuple_count == 0


def test_create_table_registers_schema(tmp_path):
    catalog = Catalog(tmp_path)

    catalog.create_table("Students", "id:INT,name:VARCHAR(50)")

    metadata = catalog.get_table("Students")

    assert metadata.schema == [
        ("id", "INT"),
        ("name", "VARCHAR(50)"),
    ]


def test_create_multiple_tables(tmp_path):
    catalog = Catalog(tmp_path)

    catalog.create_table("Students", "id:INT")
    catalog.create_table("Courses", "code:VARCHAR(20)")

    assert catalog.list_tables() == ["Students", "Courses"]


def test_create_table_persists_after_reopening(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("R", "a:INT,b:VARCHAR(20)")

    reopened = Catalog(tmp_path)

    metadata = reopened.get_table("R")

    assert metadata.name == "R"
    assert metadata.filename == "R.db"
    assert metadata.schema == [
        ("a", "INT"),
        ("b", "VARCHAR(20)"),
    ]


def test_create_table_rejects_duplicate_name(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("R", "id:INT")

    with pytest.raises(ValueError, match="Table already exists"):
        catalog.create_table("R", "name:VARCHAR(20)")


def test_create_table_rejects_reserved_name(tmp_path):
    catalog = Catalog(tmp_path)

    with pytest.raises(ValueError, match="reserved"):
        catalog.create_table("catalog", "id:INT")


def test_create_table_rejects_invalid_schema(tmp_path):
    catalog = Catalog(tmp_path)

    with pytest.raises(ValueError, match="Unsupported column type"):
        catalog.create_table("R", "price:FLOAT")

    assert not (tmp_path / "R.db").exists()
    assert catalog.list_tables() == []


def test_update_table_metadata(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("R", "id:INT,name:VARCHAR(20)")

    metadata = catalog.get_table("R")
    metadata.page_count = 5
    metadata.tuple_count = 250

    catalog.update_table(metadata)

    updated = catalog.get_table("R")

    assert updated.page_count == 5
    assert updated.tuple_count == 250
    assert updated.schema == [
        ("id", "INT"),
        ("name", "VARCHAR(20)"),
    ]


def test_update_table_persists_after_reopening(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("R", "id:INT")

    metadata = catalog.get_table("R")
    metadata.page_count = 3
    metadata.tuple_count = 100

    catalog.update_table(metadata)

    reopened = Catalog(tmp_path)
    restored = reopened.get_table("R")

    assert restored.page_count == 3
    assert restored.tuple_count == 100


def test_update_table_does_not_duplicate_entries(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("R", "id:INT")

    metadata = catalog.get_table("R")

    for count in range(1, 6):
        metadata.tuple_count = count
        catalog.update_table(metadata)

    assert catalog.list_tables() == ["R"]
    assert catalog.get_table("R").tuple_count == 5
    assert len(list(catalog.heap.scan())) == 1


def test_update_nonexistent_table_rejected(tmp_path):
    catalog = Catalog(tmp_path)

    metadata = TableMetadata(
        name="Missing",
        filename="Missing.db",
        schema=[("id", "INT")],
    )

    with pytest.raises(ValueError, match="Table does not exist"):
        catalog.update_table(metadata)
