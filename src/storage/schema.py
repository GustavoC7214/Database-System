import re

COLUMN_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VARCHAR_PATTERN = re.compile(r"^VARCHAR\((\d+)\)$")


def parse_schema(schema_text: str) -> list[tuple[str, str]]:
    """Parse a table schema into (column name, type) pairs."""
    if not isinstance(schema_text, str) or not schema_text.strip():
        raise ValueError("Schema cannot be empty")

    schema: list[tuple[str, str]] = []
    seen_names: set[str] = set()

    for column_definition in schema_text.split(","):
        parts = column_definition.strip().split(":")

        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(
                f"Invalid column definition: {column_definition.strip()}"
            )

        column_name = parts[0].strip()
        column_type = parts[1].strip().upper()

        if not COLUMN_NAME_PATTERN.fullmatch(column_name):
            raise ValueError(f"Invalid column name: {column_name}")

        if column_name in seen_names:
            raise ValueError(f"Duplicate column name: {column_name}")

        if column_type != "INT":
            match = VARCHAR_PATTERN.fullmatch(column_type)

            if match is None:
                raise ValueError(
                    f"Unsupported column type: {column_type}"
                )

            max_length = int(match.group(1))

            if not 1 <= max_length <= 255:
                raise ValueError(
                    f"VARCHAR length must be between 1 and 255: "
                    f"{column_name}"
                )

            column_type = f"VARCHAR({max_length})"

        schema.append((column_name, column_type))
        seen_names.add(column_name)

    return schema
