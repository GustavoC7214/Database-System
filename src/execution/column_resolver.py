"""Resolve qualified and unqualified execution schema columns."""


def resolve_column(
    schema: list[tuple[str, str]],
    column: str,
) -> int:
    """Return a unique column index, rejecting unknown or ambiguous names."""
    if not isinstance(column, str):
        raise TypeError("Column name must be a string")

    if "." in column:
        matches = [index for index, (name, _) in enumerate(schema) if name == column]
    else:
        matches = [
            index
            for index, (name, _) in enumerate(schema)
            if name.rsplit(".", 1)[-1] == column
        ]

    if not matches:
        raise ValueError(f"Unknown column: {column}")

    if len(matches) > 1:
        raise ValueError(f"Ambiguous column: {column}")

    return matches[0]
