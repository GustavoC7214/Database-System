from collections.abc import Generator, Iterator
from pathlib import Path

from src.execution.operator import Operator
from src.execution.page import PageKey
from src.execution.page_manager import SharedPageManager
from src.execution.page_views import DirectoryPageView, SlottedPageView
from src.storage.catalog import TableMetadata, decode_metadata
from src.storage.directory_page import NO_NEXT_PAGE
from src.storage.record_codec import decode_record


class SeqScan(Operator):
    """Sequentially scan a table using the shared page manager."""

    def __init__(
        self,
        db_dir: str | Path,
        table_name: str,
        pages: SharedPageManager,
    ) -> None:
        super().__init__()
        self.db_dir = Path(db_dir)
        self.table_name = table_name
        self.pages = pages
        self._iterator: Generator[tuple[int | str, ...], None, None] | None = None
        self._last_page_reads = 0

    def _records(self, file_path: Path) -> Iterator[bytes]:
        directory_id = 0

        while True:
            with self.pages.pinned_page(PageKey(file_path, directory_id)) as data:
                directory = DirectoryPageView(directory_id, data)
                entries = [
                    directory.get_entry(i)[0] for i in range(directory.entry_count)
                ]
                next_directory = directory.next_dir_page

            for page_id in entries:
                with self.pages.pinned_page(PageKey(file_path, page_id)) as data:
                    page = SlottedPageView(page_id, data)

                    for slot_no in range(page.slot_count):
                        offset, _ = page.get_slot(slot_no)

                        if offset != 0:
                            yield page.get(slot_no)

            if next_directory == NO_NEXT_PAGE:
                return

            directory_id = next_directory

    def _find_table(self) -> TableMetadata:
        catalog_path = self.db_dir / "catalog.db"

        for record in self._records(catalog_path):
            metadata = decode_metadata(record)

            if metadata.name == self.table_name:
                return metadata

        raise ValueError(f"Table does not exist: {self.table_name}")

    def open(self) -> None:
        self._last_page_reads = self.pages.reads
        metadata = self._find_table()

        self.schema = [
            (f"{self.table_name}.{name}", column_type)
            for name, column_type in metadata.schema
        ]

        table_path = self.db_dir / metadata.filename
        self._iterator = (
            decode_record(record, metadata.schema)
            for record in self._records(table_path)
        )

        self._counters.tuples_out = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._counters.comparisons = 0
        self._counters.page_reads = self.pages.reads - self._last_page_reads
        self._last_page_reads = self.pages.reads

    def next(self) -> tuple[int | str, ...] | None:
        if self._iterator is None:
            raise RuntimeError("SeqScan is not open")

        try:
            row = next(self._iterator)
        except StopIteration:
            return None
        finally:
            current_reads = self.pages.reads
            self._counters.page_reads += current_reads - self._last_page_reads
            self._last_page_reads = current_reads

        self._counters.tuples_out += 1
        return row

    def close(self) -> None:
        if self._iterator is not None:
            self._iterator.close()

        self._iterator = None
