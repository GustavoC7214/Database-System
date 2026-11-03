"""Tests for the Module 3 catalog adapter."""

from pathlib import Path
from typing import cast

import pytest

from src.sql.catalog import ColumnSchema, SchemaCatalog, TableSchema
from src.storage.catalog import Catalog, TableMetadata


class FakeCatalog:
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
                ],
            ),
            "Dept": TableMetadata(
                name="Dept",
                filename="Dept.db",
                schema=[
                    ("did", "INT"),
                    ("title", "VARCHAR(60)"),
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
def catalog() -> SchemaCatalog:
    fake = FakeCatalog()
    return SchemaCatalog(cast(Catalog, fake))


def test_get_table(catalog: SchemaCatalog):
    table = catalog.get_table("Emp")

    assert isinstance(table, TableSchema)
    assert table.name == "Emp"
    assert len(table.columns) == 4


def test_column_order(catalog: SchemaCatalog):
    table = catalog.get_table("Emp")

    assert [column.name for column in table.columns] == [
        "eid",
        "name",
        "age",
        "did",
    ]


def test_column_types(catalog: SchemaCatalog):
    table = catalog.get_table("Emp")

    assert table.get_column("age") == ColumnSchema("age", "INT")
    assert table.get_column("name") == ColumnSchema("name", "VARCHAR(40)")


def test_unknown_column(catalog: SchemaCatalog):
    table = catalog.get_table("Emp")

    assert table.get_column("salary") is None


def test_unknown_table(catalog: SchemaCatalog):
    with pytest.raises(ValueError, match="Unknown table: Missing"):
        catalog.get_table("Missing")


def test_table_names_case_sensitive(catalog: SchemaCatalog):
    with pytest.raises(ValueError, match="Unknown table: emp"):
        catalog.get_table("emp")


def test_column_names_case_sensitive(catalog: SchemaCatalog):
    table = catalog.get_table("Emp")

    assert table.get_column("Age") is None
    assert table.get_column("age") is not None


def test_list_tables(catalog: SchemaCatalog):
    assert catalog.list_tables() == ("Emp", "Dept")


def test_missing_database_directory(tmp_path: Path):
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="Database directory does not exist"):
        SchemaCatalog.from_directory(missing)

    assert not missing.exists()


def test_missing_catalog_file(tmp_path: Path):
    with pytest.raises(ValueError, match="Database catalog does not exist"):
        SchemaCatalog.from_directory(tmp_path)

    assert not (tmp_path / "catalog.db").exists()
