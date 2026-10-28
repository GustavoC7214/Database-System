import json
import struct
from pathlib import Path
from typing import Protocol, Self, cast

from src.execution.temp_page import decode_temp_page
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]


class _ReadableInto(Protocol):
    def readinto(self, buffer: memoryview) -> int: ...


class TempPageReader:
    """Read tuples from a temporary file containing fixed-size pages."""

    def __init__(
        self,
        path: Path,
        buffer: memoryview | None = None,
    ) -> None:
        if buffer is not None and (buffer.readonly or len(buffer) != PAGE_SIZE):
            raise ValueError("Temporary reader requires a writable 4096-byte buffer")

        self._buffer = buffer
        self._file = path.open("rb", buffering=0 if buffer is not None else -1)
        self._payload = b""
        self._offset = 0
        self._closed = False
        self.page_reads = 0

    def _load_page(self) -> bool:
        if self._buffer is None:
            page = self._file.read(PAGE_SIZE)
        else:
            # Drop the previous page slice before reusing its backing frame.
            self._payload = b""
            count = cast(_ReadableInto, self._file).readinto(self._buffer)
            if count == 0:
                return False

            if count != PAGE_SIZE:
                raise ValueError("Truncated temporary page")

            page = self._buffer

        if not page:
            return False

        if len(page) != PAGE_SIZE:
            raise ValueError("Truncated temporary page")

        self._payload = decode_temp_page(page)
        self._offset = 0
        self.page_reads += 1

        return True

    def read(self) -> Row | None:
        if self._closed:
            raise RuntimeError("Temporary reader is closed")

        while self._offset >= len(self._payload):
            if not self._load_page():
                return None

        if len(self._payload) - self._offset < 4:
            raise ValueError("Truncated temporary record header")

        (length,) = struct.unpack_from(
            "<I",
            self._payload,
            self._offset,
        )

        self._offset += 4
        end = self._offset + length

        if end > len(self._payload):
            raise ValueError("Temporary record crosses page boundary")

        encoded = self._payload[self._offset : end]
        self._offset = end
        row = json.loads(bytes(encoded).decode("utf-8"))

        if not isinstance(row, list):
            raise TypeError("Invalid temporary tuple")

        return tuple(row)

    def close(self) -> None:
        if self._closed:
            return

        self._payload = b""
        self._file.close()
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
