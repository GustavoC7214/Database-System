from pathlib import Path

from src.storage.buffer_pool import BufferPool
from src.storage.directory_page import (
    MAX_ENTRIES,
    NO_NEXT_PAGE,
    DirectoryPage,
)
from src.storage.disk_manager import DiskManager
from src.storage.slotted_page import SlottedPage


class HeapFile:
    def __init__(
        self,
        file_path: str | Path,
        frames: int = 8,
        policy: str = "lru",
    ) -> None:
        self.disk = DiskManager(file_path)
        self.buffer = BufferPool(
            self.disk,
            frames=frames,
            policy=policy,
        )

        if self.disk.page_count() == 0:
            page_id, data = self.buffer.new_page()

            try:
                directory = DirectoryPage(page_id)
                data[:] = directory.to_bytes()
            finally:
                self.buffer.unpin_page(page_id, dirty=True)

            self.buffer.flush_all()

        self._validate_directory_page()

    def _validate_directory_page(self) -> None:
        data = self.buffer.fetch_page(0)

        try:
            DirectoryPage(0, bytes(data))
        finally:
            self.buffer.unpin_page(0)

    @property
    def page_count(self) -> int:
        return self.disk.page_count()

    def flush(self) -> None:
        """Persist all dirty heap-file pages to disk."""
        self.buffer.flush_all()

    def insert(self, record: bytes) -> tuple[int, int]:
        if len(record) + 4 > 4088:
            raise ValueError(
                f"Record is too large for a 4096-byte page: {len(record)} bytes"
            )

        directory_id = 0

        while True:
            # Read the current directory page through the Buffer Pool.
            directory_data = self.buffer.fetch_page(directory_id)

            try:
                directory = DirectoryPage(
                    directory_id,
                    bytes(directory_data),
                )
            finally:
                self.buffer.unpin_page(directory_id)

            # Try inserting into an existing data page.
            for index in range(directory.entry_count):
                data_page_id, free_bytes = directory.get_entry(index)

                if free_bytes < len(record) + 4:
                    continue

                data = self.buffer.fetch_page(data_page_id)
                dirty = False

                try:
                    page = SlottedPage(data_page_id, bytes(data))
                    slot_no = page.insert(record)

                    if slot_no is None:
                        raise RuntimeError(
                            "Directory free-space information is inconsistent"
                        )

                    data[:] = page.to_bytes()
                    dirty = True
                    new_free_space = page.free_space
                finally:
                    self.buffer.unpin_page(
                        data_page_id,
                        dirty=dirty,
                    )

                # Update the directory's free-space information.
                directory.update_entry(index, new_free_space)

                directory_data = self.buffer.fetch_page(directory_id)

                try:
                    directory_data[:] = directory.to_bytes()
                finally:
                    self.buffer.unpin_page(
                        directory_id,
                        dirty=True,
                    )

                return data_page_id, slot_no

            # Continue searching the next directory page.
            if directory.next_dir_page != NO_NEXT_PAGE:
                directory_id = directory.next_dir_page
                continue

            # Allocate a new directory if the current one is full.
            if directory.entry_count >= MAX_ENTRIES:
                new_directory_id, new_directory_data = self.buffer.new_page()

                try:
                    new_directory = DirectoryPage(new_directory_id)
                    new_directory_data[:] = new_directory.to_bytes()
                finally:
                    self.buffer.unpin_page(
                        new_directory_id,
                        dirty=True,
                    )

                # Link the previous directory to the new directory.
                directory.next_dir_page = new_directory_id

                directory_data = self.buffer.fetch_page(directory_id)

                try:
                    directory_data[:] = directory.to_bytes()
                finally:
                    self.buffer.unpin_page(
                        directory_id,
                        dirty=True,
                    )

                directory_id = new_directory_id
                directory = new_directory

            # Allocate a new data page through the Buffer Pool.
            data_page_id, data = self.buffer.new_page()

            try:
                page = SlottedPage(data_page_id)
                slot_no = page.insert(record)

                if slot_no is None:
                    raise RuntimeError("Record could not fit in an empty page")

                data[:] = page.to_bytes()
                new_free_space = page.free_space
            finally:
                self.buffer.unpin_page(
                    data_page_id,
                    dirty=True,
                )

            # Register the new data page in the directory.
            directory.add_entry(data_page_id, new_free_space)

            directory_data = self.buffer.fetch_page(directory_id)

            try:
                directory_data[:] = directory.to_bytes()
            finally:
                self.buffer.unpin_page(
                    directory_id,
                    dirty=True,
                )

            return data_page_id, slot_no

    def _validate_record_page(self, page_id: int) -> None:
        """Ensure the page ID belongs to a registered data page."""
        directory_id = 0

        while True:
            data = self.buffer.fetch_page(directory_id)

            try:
                directory = DirectoryPage(directory_id, bytes(data))
            finally:
                self.buffer.unpin_page(directory_id)

            for index in range(directory.entry_count):
                registered_page_id, _ = directory.get_entry(index)

                if registered_page_id == page_id:
                    return

            if directory.next_dir_page == NO_NEXT_PAGE:
                break

            directory_id = directory.next_dir_page

        raise ValueError(f"Invalid record page: {page_id}")

    def get(self, rid: tuple[int, int]) -> bytes:
        page_id, slot_no = rid

        self._validate_record_page(page_id)

        data = self.buffer.fetch_page(page_id)

        try:
            page = SlottedPage(page_id, bytes(data))
            return page.get(slot_no)
        finally:
            self.buffer.unpin_page(page_id)

    def delete(self, rid: tuple[int, int]) -> None:
        page_id, slot_no = rid

        self._validate_record_page(page_id)

        data = self.buffer.fetch_page(page_id)
        dirty = False

        try:
            page = SlottedPage(page_id, bytes(data))
            page.delete(slot_no)

            data[:] = page.to_bytes()
            dirty = True
        finally:
            self.buffer.unpin_page(page_id, dirty=dirty)

    def scan(self):
        """Lazily yield (RID, record) pairs for all live records."""
        directory_id = 0

        while True:
            # Fetch and read the current directory page.
            directory_data = self.buffer.fetch_page(directory_id)

            try:
                directory = DirectoryPage(
                    directory_id,
                    bytes(directory_data),
                )
            finally:
                self.buffer.unpin_page(directory_id)

            # Visit each data page listed in the directory.
            for index in range(directory.entry_count):
                data_page_id, _ = directory.get_entry(index)

                data = self.buffer.fetch_page(data_page_id)

                try:
                    page = SlottedPage(
                        data_page_id,
                        bytes(data),
                    )
                finally:
                    self.buffer.unpin_page(data_page_id)

                # Yield only live records.
                for slot_no in range(page.slot_count):
                    offset, _ = page.get_slot(slot_no)

                    if offset == 0:
                        continue

                    yield (
                        (data_page_id, slot_no),
                        page.get(slot_no),
                    )

            if directory.next_dir_page == NO_NEXT_PAGE:
                break

            directory_id = directory.next_dir_page
