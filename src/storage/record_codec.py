
import struct


def encode_int(value: int) -> bytes:
    """Encode an integer as a signed 4-byte little-endian value."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("INT value must be an integer")

    if not -(2**31) <= value <= 2**31 - 1:
        raise ValueError("INT value is outside the signed 32-bit range")

    return struct.pack("<i", value)


def decode_int(data: bytes) -> int:
    """Decode a signed 4-byte little-endian integer."""
    if len(data) != 4:
        raise ValueError("INT data must be exactly 4 bytes")

    return struct.unpack("<i", data)[0]


def encode_varchar(value: str, max_length: int) -> bytes:
    """Encode a UTF-8 string with a 2-byte length prefix."""
    if not isinstance(value, str):
        raise TypeError("VARCHAR value must be a string")

    if not 1 <= max_length <= 255:
        raise ValueError("VARCHAR length must be between 1 and 255")

    encoded = value.encode("utf-8")

    if len(encoded) > max_length:
        raise ValueError(
            f"VARCHAR value is {len(encoded)} bytes, "
            f"maximum is {max_length}"
        )

    return struct.pack("<H", len(encoded)) + encoded

def decode_varchar(data: bytes, max_length: int) -> str:
    """Decode a length-prefixed UTF-8 string."""
    if not 1 <= max_length <= 255:
        raise ValueError("VARCHAR length must be between 1 and 255")

    if len(data) < 2:
        raise ValueError("VARCHAR data is missing its length prefix")

    length = struct.unpack_from("<H", data, 0)[0]

    if length > max_length:
        raise ValueError("VARCHAR length exceeds schema limit")

    if len(data) != length + 2:
        raise ValueError("VARCHAR data length does not match prefix")

    return data[2:].decode("utf-8")

def encode_record(
    values: tuple[int | str, ...],
    schema: list[tuple[str, str]],
) -> bytes:
    """Encode a complete record according to its schema."""
    if len(values) != len(schema):
        raise ValueError(
            f"Expected {len(schema)} values, received {len(values)}"
        )

    result = bytearray()

    for value, (column_name, column_type) in zip(values, schema):
        if column_type == "INT":
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"Column {column_name} requires INT")

            result.extend(encode_int(value))

        elif column_type.startswith("VARCHAR(") and column_type.endswith(")"):
            try:
                max_length = int(column_type[8:-1])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid type for column {column_name}: {column_type}"
                ) from exc

            if not isinstance(value, str):
                raise TypeError(f"Column {column_name} requires VARCHAR")

            result.extend(encode_varchar(value, max_length))

        else:
            raise ValueError(
                f"Unsupported type for column {column_name}: {column_type}"
            )

    return bytes(result)

def decode_record(
    data: bytes,
    schema: list[tuple[str, str]],
) -> tuple[int | str, ...]:
    """Decode a complete binary record according to its schema."""
    values: list[int | str] = []
    offset = 0

    for column_name, column_type in schema:
        if column_type == "INT":
            if offset + 4 > len(data):
                raise ValueError(
                    f"Insufficient data for INT column {column_name}"
                )

            values.append(decode_int(data[offset:offset + 4]))
            offset += 4

        elif column_type.startswith("VARCHAR(") and column_type.endswith(")"):
            try:
                max_length = int(column_type[8:-1])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid type for column {column_name}: {column_type}"
                ) from exc

            if not 1 <= max_length <= 255:
                raise ValueError(
                    f"Invalid VARCHAR length for column {column_name}"
                )

            if offset + 2 > len(data):
                raise ValueError(
                    f"Missing VARCHAR length for column {column_name}"
                )

            length = int.from_bytes(
                data[offset:offset + 2], byteorder="little"
            )

            end = offset + 2 + length

            if end > len(data):
                raise ValueError(
                    f"Truncated VARCHAR data for column {column_name}"
                )

            values.append(decode_varchar(data[offset:end], max_length))
            offset = end

        else:
            raise ValueError(
                f"Unsupported type for column {column_name}: {column_type}"
            )

    if offset != len(data):
        raise ValueError(
            f"Record contains {len(data) - offset} unexpected trailing bytes"
        )

    return tuple(values)
