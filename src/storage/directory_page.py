
import struct

from src.storage.disk_manager import PAGE_SIZE
from src.storage.slotted_page import HEADER_SIZE as SLOTTED_HEADER_SIZE

HEADER_SIZE = 10
ENTRY_SIZE = 6
MAX_ENTRIES = (PAGE_SIZE - HEADER_SIZE) // ENTRY_SIZE
NO_NEXT_PAGE = 0xFFFFFFFF


class DirectoryPage:
    def __init__(self, page_id: int, data: bytes | None = None) -> None:
        if page_id < 0 or page_id >= NO_NEXT_PAGE:
            raise ValueError("Invalid directory page ID")

        if data is None:
            self.data = bytearray(PAGE_SIZE)
            struct.pack_into(
                "<IIH",
                self.data,
                0,
                page_id,
                NO_NEXT_PAGE,
                0,
            )
        else:
            if len(data) != PAGE_SIZE:
                raise ValueError("Directory page must be exactly 4096 bytes")

            self.data = bytearray(data)

            if self.page_id != page_id:
                raise ValueError("Directory page ID does not match data")

    @property
    def page_id(self) -> int:
        return struct.unpack_from("<I", self.data, 0)[0]

    @property
    def next_dir_page(self) -> int:
        return struct.unpack_from("<I", self.data, 4)[0]

    @next_dir_page.setter
    def next_dir_page(self, page_id: int) -> None:
        if page_id < 0 or page_id > NO_NEXT_PAGE:
            raise ValueError("Invalid next directory page ID")

        struct.pack_into("<I", self.data, 4, page_id)

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

    def add_entry(self, data_page_id: int, free_bytes: int) -> int:
        if self.entry_count >= MAX_ENTRIES:
            raise ValueError("Directory page is full")

        self._validate_entry(data_page_id, free_bytes)

        index = self.entry_count

        struct.pack_into(
            "<IH",
            self.data,
            HEADER_SIZE + ENTRY_SIZE * index,
            data_page_id,
            free_bytes,
        )

        struct.pack_into("<H", self.data, 8, index + 1)

        return index

    def update_entry(self, index: int, free_bytes: int) -> None:
        data_page_id, _ = self.get_entry(index)

        self._validate_entry(data_page_id, free_bytes)

        struct.pack_into(
            "<IH",
            self.data,
            HEADER_SIZE + ENTRY_SIZE * index,
            data_page_id,
            free_bytes,
        )

    @staticmethod
    def _validate_entry(data_page_id: int, free_bytes: int) -> None:
        if data_page_id < 0 or data_page_id >= NO_NEXT_PAGE:
            raise ValueError("Invalid data page ID")

        if free_bytes < 0 or free_bytes > PAGE_SIZE - SLOTTED_HEADER_SIZE:
            raise ValueError("Invalid free-space value")

    def to_bytes(self) -> bytes:
        return bytes(self.data)
