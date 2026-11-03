"""Read-only schema access for the Module 3 SQL front end."""

from dataclasses import dataclass
from pathlib import Path

from src.storage.catalog import Catalog


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """A column's name and declared SQL type."""

    name: str
    data_type: str


@dataclass(frozen=True, slots=True)
class TableSchema:
    """An ordered table schema used during SQL name resolution."""

    name: str
    columns: tuple[ColumnSchema, ...]

    def get_column(self, name: str) -> ColumnSchema | None:
        """Find a column by its case-sensitive name."""
        for column in self.columns:
            if column.name == name:
                return column
        return None


class SchemaCatalog:
    """Adapter over the existing Module 1 persistent catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    @classmethod
    def from_directory(cls, db_dir: str | Path) -> "SchemaCatalog":
        """Open an existing database without creating a new directory."""
        path = Path(db_dir)

        if not path.is_dir():
            raise ValueError(f"Database directory does not exist: {path}")

        if not (path / "catalog.db").is_file():
            raise ValueError(f"Database catalog does not exist: {path}")

        return cls(Catalog(path))

    def get_table(self, name: str) -> TableSchema:
        """Return a table's ordered schema.

        Unknown tables are reported using the original table name.
        """
        try:
            metadata = self._catalog.get_table(name)
        except ValueError as exc:
            raise ValueError(f"Unknown table: {name}") from exc

        return TableSchema(
            name=metadata.name,
            columns=tuple(
                ColumnSchema(column_name, column_type)
                for column_name, column_type in metadata.schema
            ),
        )

    def list_tables(self) -> tuple[str, ...]:
        """List registered table names."""
        return tuple(self._catalog.list_tables())
