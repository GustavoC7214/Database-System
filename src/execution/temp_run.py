import json
import struct
from collections.abc import Generator
from pathlib import Path


def tuple_size(row: tuple[int | str | float, ...]) -> int:
    """Return the serialized size of a tuple, including its length header."""
    payload = json.dumps(
        row,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    return 4 + len(payload)


def write_tuple(file, row: tuple[int | str | float, ...]) -> int:
    """Write one length-prefixed tuple and return the bytes written."""
    payload = json.dumps(
        row,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    file.write(struct.pack("<I", len(payload)))
    file.write(payload)

    return 4 + len(payload)


def read_tuples(path: Path) -> Generator[tuple[int | str | float, ...]]:
    """Read tuples from a temporary run file."""
    with path.open("rb") as file:
        while True:
            header = file.read(4)

            if not header:
                return

            if len(header) != 4:
                raise ValueError("Truncated temporary-run header")

            (length,) = struct.unpack("<I", header)
            payload = file.read(length)

            if len(payload) != length:
                raise ValueError("Truncated temporary-run record")

            row = json.loads(payload.decode("utf-8"))

            if not isinstance(row, list):
                raise TypeError("Invalid temporary-run tuple")

            yield tuple(row)
