
import struct

from src.storage.disk_manager import PAGE_SIZE

HEADER_SIZE = 8
SLOT_SIZE = 4


class SlottedPage:
    def __init__(self, page_id: int, data: bytes | None = None) -> None:
        if page_id < 0 or page_id > 0xFFFFFFFF:
            raise ValueError("Invalid page ID")

        if data is None:
            self.data = bytearray(PAGE_SIZE)
            struct.pack_into("<IHH", self.data, 0, page_id, 0, PAGE_SIZE)
        else:
            if len(data) != PAGE_SIZE:
                raise ValueError("Page data must be exactly 4096 bytes")

            self.data = bytearray(data)

            if self.page_id != page_id:
                raise ValueError("Page ID does not match page data")

    @property
    def page_id(self) -> int:
        return struct.unpack_from("<I", self.data, 0)[0]

    @property
    def slot_count(self) -> int:
        return struct.unpack_from("<H", self.data, 4)[0]

    @property
    def free_end(self) -> int:
        return struct.unpack_from("<H", self.data, 6)[0]

    @property
    def free_space(self) -> int:
        return self.free_end - (HEADER_SIZE + SLOT_SIZE * self.slot_count)

    def get_slot(self, slot_no: int) -> tuple[int, int]:
        if slot_no < 0 or slot_no >= self.slot_count:
            raise ValueError(f"Invalid slot number: {slot_no}")

        return struct.unpack_from(
            "<HH", self.data, HEADER_SIZE + SLOT_SIZE * slot_no
        )

    def insert(self, record: bytes) -> int | None:
        length = len(record)

        if length > PAGE_SIZE - HEADER_SIZE - SLOT_SIZE:
            raise ValueError(
                f"Record is too large for a slotted page: "
                f"{length} bytes"
            )

        if self.free_space < length + SLOT_SIZE:
            return None

        slot_no = self.slot_count
        new_free_end = self.free_end - length

        self.data[new_free_end : new_free_end + length] = record

        struct.pack_into(
            "<HH",
            self.data,
            HEADER_SIZE + SLOT_SIZE * slot_no,
            new_free_end,
            length,
        )

        struct.pack_into("<H", self.data, 4, slot_no + 1)
        struct.pack_into("<H", self.data, 6, new_free_end)

        return slot_no

    def get(self, slot_no: int) -> bytes:
        offset, length = self.get_slot(slot_no)

        if offset == 0:
            raise ValueError(
                f"Record ({self.page_id}, {slot_no}) has been deleted"
            )

        return bytes(self.data[offset : offset + length])

    def delete(self, slot_no: int) -> None:
        offset, _ = self.get_slot(slot_no)

        if offset == 0:
            raise ValueError(
                f"Record ({self.page_id}, {slot_no}) is already deleted"
            )

        struct.pack_into(
            "<HH",
            self.data,
            HEADER_SIZE + SLOT_SIZE * slot_no,
            0,
            0,
        )

    def to_bytes(self) -> bytes:
        return bytes(self.data)
