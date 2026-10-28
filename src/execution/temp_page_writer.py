import json
import struct
from pathlib import Path
from typing import Self

from src.execution.temp_page import PAYLOAD_SIZE, encode_temp_page
from src.storage.disk_manager import PAGE_SIZE

Row = tuple[int | str | float, ...]


class TempPageWriter:
    """Write tuples to a temporary file in fixed-size pages."""

    def __init__(
        self,
        path: Path,
        buffer: memoryview | None = None,
    ) -> None:
        if buffer is not None and (buffer.readonly or len(buffer) != PAGE_SIZE):
            raise ValueError("Temporary writer requires a writable 4096-byte buffer")

        self._file = path.open("wb")
        self._buffer = buffer
        self._payload = bytearray() if buffer is None else None
        self._used = 0
        self.page_writes = 0
        self._closed = False

    def write(self, row: Row) -> None:
        if self._closed:
            raise RuntimeError("Temporary writer is closed")

        encoded = json.dumps(
            row,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        record = struct.pack("<I", len(encoded)) + encoded

        if len(record) > PAYLOAD_SIZE:
            raise ValueError("Tuple exceeds temporary-page capacity")

        if self._buffer is None:
            assert self._payload is not None

            if len(self._payload) + len(record) > PAYLOAD_SIZE:
                self._flush_page()

            self._payload.extend(record)
        else:
            if self._used + len(record) > PAYLOAD_SIZE:
                self._flush_page()

            start = 4 + self._used
            self._buffer[start : start + len(record)] = record
            self._used += len(record)

    def _flush_page(self) -> None:
        if self._buffer is None:
            assert self._payload is not None

            if not self._payload:
                return

            page = encode_temp_page(bytes(self._payload))
            self._file.write(page)
            self._payload.clear()
        else:
            if self._used == 0:
                return

            struct.pack_into("<I", self._buffer, 0, self._used)

            # Fill unused space so every physical page is deterministic.
            self._buffer[4 + self._used :] = bytes(PAGE_SIZE - 4 - self._used)

            self._file.write(self._buffer)

            self._used = 0

        self.page_writes += 1

    def close(self) -> None:
        if self._closed:
            return

        try:
            self._flush_page()
        finally:
            self._file.close()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
