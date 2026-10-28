import struct

from src.storage.directory_page import (
    ENTRY_SIZE,
    HEADER_SIZE,
)
from src.storage.disk_manager import PAGE_SIZE
from src.storage.slotted_page import HEADER_SIZE as SLOTTED_HEADER_SIZE
from src.storage.slotted_page import SLOT_SIZE


class DirectoryPageView:
    """Read a directory page without copying its underlying buffer."""

    def __init__(self, page_id: int, data: memoryview) -> None:
        if len(data) != PAGE_SIZE:
            raise ValueError("Directory page must be exactly 4096 bytes")

        self.data = data

        if self.page_id != page_id:
            raise ValueError("Directory page ID does not match data")

    @property
    def page_id(self) -> int:
        return struct.unpack_from("<I", self.data, 0)[0]

    @property
    def next_dir_page(self) -> int:
        return struct.unpack_from("<I", self.data, 4)[0]

    @property
    def entry_count(self) -> int:
        return struct.unpack_from("<H", self.data, 8)[0]

    def get_entry(self, index: int) -> tuple[int, int]:
        if index < 0 or index >= self.entry_count:
            raise ValueError(f"Invalid directory entry: {index}")

        return struct.unpack_from(
            "<IH",
            self.data,
            HEADER_SIZE + ENTRY_SIZE * index,
        )


class SlottedPageView:
    """Read records from an existing page frame without copying the page."""

    def __init__(self, page_id: int, data: memoryview) -> None:
        if len(data) != PAGE_SIZE:
            raise ValueError("Slotted page must be exactly 4096 bytes")

        self.data = data

        if self.page_id != page_id:
            raise ValueError("Page ID does not match page data")

    @property
    def page_id(self) -> int:
        return struct.unpack_from("<I", self.data, 0)[0]

    @property
    def slot_count(self) -> int:
        return struct.unpack_from("<H", self.data, 4)[0]

    def get_slot(self, slot_no: int) -> tuple[int, int]:
        if slot_no < 0 or slot_no >= self.slot_count:
            raise ValueError(f"Invalid slot number: {slot_no}")

        return struct.unpack_from(
            "<HH",
            self.data,
            SLOTTED_HEADER_SIZE + SLOT_SIZE * slot_no,
        )

    def get(self, slot_no: int) -> bytes:
        offset, length = self.get_slot(slot_no)

        if offset == 0:
            raise ValueError(f"Record ({self.page_id}, {slot_no}) has been deleted")

        if offset + length > PAGE_SIZE:
            raise ValueError("Record extends beyond page boundary")

        return bytes(self.data[offset : offset + length])
