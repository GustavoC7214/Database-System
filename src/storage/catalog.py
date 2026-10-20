import json
from dataclasses import dataclass
from pathlib import Path

from src.storage.heap_file import HeapFile
from src.storage.schema import parse_schema


@dataclass
class TableMetadata:
    """Metadata describing a table stored in the database."""

    name: str
    filename: str
    schema: list[tuple[str, str]]
    page_count: int = 0
    tuple_count: int = 0


def encode_metadata(metadata: TableMetadata) -> bytes:
    """Serialize table metadata into UTF-8 JSON bytes."""
    data = {
        "name": metadata.name,
        "filename": metadata.filename,
        "schema": metadata.schema,
        "page_count": metadata.page_count,
        "tuple_count": metadata.tuple_count,
    }

    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_metadata(data: bytes) -> TableMetadata:
    """Deserialize UTF-8 JSON bytes into table metadata."""
    decoded = json.loads(data.decode("utf-8"))

    return TableMetadata(
        name=decoded["name"],
        filename=decoded["filename"],
        schema=[tuple(column) for column in decoded["schema"]],
        page_count=decoded["page_count"],
        tuple_count=decoded["tuple_count"],
    )


class Catalog:
    """Persistent table metadata stored in catalog.db."""

    def __init__(
        self,
        db_dir: str | Path,
        frames: int = 8,
        policy: str = "lru",
    ) -> None:
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.heap = HeapFile(
            self.db_dir / "catalog.db",
            frames=frames,
            policy=policy,
        )

    def get_table(self, name: str) -> TableMetadata:
        """Return metadata for a table by name."""
        for _, record in self.heap.scan():
            metadata = decode_metadata(record)

            if metadata.name == name:
                return metadata

        raise ValueError(f"Table does not exist: {name}")

    def update_table(self, metadata: TableMetadata) -> None:
        """Replace a table's stored metadata."""
        for rid, record in self.heap.scan():
            existing = decode_metadata(record)

            if existing.name == metadata.name:
                # Insert the replacement before deleting the old record.
                self.heap.insert(encode_metadata(metadata))
                self.heap.delete(rid)
                self.heap.flush()
                return

        raise ValueError(f"Table does not exist: {metadata.name}")

    def list_tables(self) -> list[str]:
        """Return the names of all registered tables."""
        names = []

        for _, record in self.heap.scan():
            metadata = decode_metadata(record)
            names.append(metadata.name)

        return names

    def flush(self) -> None:
        self.heap.flush()

    def create_table(self, name: str, schema_text: str) -> TableMetadata:
        if not name.isidentifier() or not name.isascii():
            raise ValueError(f"Invalid table name: {name}")

        if name == "catalog":
            raise ValueError("Table name is reserved: catalog")

        if name in self.list_tables():
            raise ValueError(f"Table already exists: {name}")

        schema = parse_schema(schema_text)
        filename = f"{name}.db"
        table_path = self.db_dir / filename

        if table_path.exists():
            raise ValueError(f"Table file already exists: {filename}")

        heap = HeapFile(table_path)

        metadata = TableMetadata(
            name=name,
            filename=filename,
            schema=schema,
            page_count=heap.page_count,
            tuple_count=0,
        )

        self.heap.insert(encode_metadata(metadata))
        self.heap.flush()

        return metadata
