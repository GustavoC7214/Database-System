import struct

from src.storage.disk_manager import PAGE_SIZE

HEADER_SIZE = 4
PAYLOAD_SIZE = PAGE_SIZE - HEADER_SIZE


def encode_temp_page(payload: bytes) -> bytes:
    """Encode payload into one fixed-size temporary page."""
    if len(payload) > PAYLOAD_SIZE:
        raise ValueError("Temporary-page payload exceeds capacity")

    page = bytearray(PAGE_SIZE)
    struct.pack_into("<I", page, 0, len(payload))
    page[HEADER_SIZE : HEADER_SIZE + len(payload)] = payload

    return bytes(page)


def decode_temp_page(
    page: bytes | memoryview,
) -> bytes | memoryview:
    if len(page) != PAGE_SIZE:
        raise ValueError("Invalid temporary-page size")

    (length,) = struct.unpack_from("<I", page, 0)

    if length > PAYLOAD_SIZE:
        raise ValueError("Invalid temporary-page payload length")

    return page[HEADER_SIZE : HEADER_SIZE + length]
