import csv
from pathlib import Path

from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def convert_csv_row(
    row: list[str],
    schema: list[tuple[str, str]],
    row_number: int,
) -> tuple[int | str, ...]:
    """Convert CSV fields to typed values according to the schema."""
    if len(row) != len(schema):
        raise ValueError(
            f"CSV row {row_number}: expected {len(schema)} columns, "
            f"received {len(row)}"
        )

    values: list[int | str] = []

    for column_number, (text, (column_name, column_type)) in enumerate(
        zip(row, schema),
        start=1,
    ):
        if column_type == "INT":
            try:
                value = int(text)
            except ValueError as exc:
                raise ValueError(
                    f"CSV row {row_number}, column {column_number} "
                    f"({column_name}): invalid INT value {text!r}"
                ) from exc

            if not -(2**31) <= value <= 2**31 - 1:
                raise ValueError(
                    f"CSV row {row_number}, column {column_number} "
                    f"({column_name}): INT outside signed 32-bit range"
                )

            values.append(value)

        elif column_type.startswith("VARCHAR(") and column_type.endswith(")"):
            max_length = int(column_type[8:-1])
            byte_length = len(text.encode("utf-8"))

            if byte_length > max_length:
                raise ValueError(
                    f"CSV row {row_number}, column {column_number} "
                    f"({column_name}): VARCHAR is {byte_length} bytes, "
                    f"maximum is {max_length}"
                )

            values.append(text)

        else:
            raise ValueError(
                f"CSV row {row_number}, column {column_number} "
                f"({column_name}): unsupported type {column_type}"
            )

    return tuple(values)


def load_csv(
    db_dir: str | Path,
    table_name: str,
    csv_path: str | Path,
    frames: int = 8,
    policy: str = "lru",
) -> int:
    """Load a headerless CSV file into an existing table."""
    catalog = Catalog(db_dir, frames=frames, policy=policy)
    metadata = catalog.get_table(table_name)

    heap = HeapFile(
        Path(db_dir) / metadata.filename,
        frames=frames,
        policy=policy,
    )

    inserted_count = 0
    reader = None

    try:
        with open(csv_path, newline="", encoding="utf-8") as file:
            reader = csv.reader(file, strict=True)

            for row_number, row in enumerate(reader, start=1):

                try:
                    values = convert_csv_row(
                        row,
                        metadata.schema,
                        row_number,
                    )
                    record = encode_record(values, metadata.schema)
                except ValueError as exc:
                    raise ValueError(
                        f"Table {table_name}: {exc}"
                    ) from exc

                try:
                    heap.insert(record)
                except ValueError as exc:
                    raise ValueError(
                        f"Table {table_name}, CSV row {row_number}: "
                        f"{exc}"
                    ) from exc

                inserted_count += 1

    except csv.Error as exc:
        line_number = reader.line_num if reader is not None else 0

        raise ValueError(
            f"Table {table_name}: malformed CSV at line "
            f"{line_number}, column unknown: {exc}"
        ) from exc


    finally:
        # Persist successfully inserted records even if a later
        # CSV row is invalid.
        heap.flush()

        metadata.page_count = heap.page_count
        metadata.tuple_count += inserted_count
        catalog.update_table(metadata)

    return inserted_count
