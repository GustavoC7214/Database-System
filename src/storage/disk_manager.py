
from pathlib import Path

PAGE_SIZE = 4096


class DiskManager:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.touch(exist_ok=True)

    def page_count(self) -> int:
        size = self.file_path.stat().st_size

        if size % PAGE_SIZE != 0:
            raise ValueError("Database file size is not a multiple of 4096")

        return size // PAGE_SIZE

    def read_page(self, page_id: int) -> bytes:
        if page_id < 0 or page_id >= self.page_count():
            raise ValueError(f"Invalid page ID: {page_id}")

        with self.file_path.open("rb") as file:
            file.seek(page_id * PAGE_SIZE)
            data = file.read(PAGE_SIZE)

        if len(data) != PAGE_SIZE:
            raise OSError(f"Failed to read page {page_id}")

        return data

    def write_page(self, page_id: int, data: bytes) -> None:
        if page_id < 0 or page_id > self.page_count():
            raise ValueError(f"Invalid page ID: {page_id}")

        if len(data) != PAGE_SIZE:
            raise ValueError("Page data must be exactly 4096 bytes")

        with self.file_path.open("r+b") as file:
            file.seek(page_id * PAGE_SIZE)
            file.write(data)

    def allocate_page(self) -> int:
        page_id = self.page_count()
        self.write_page(page_id, bytes(PAGE_SIZE))
        return page_id
