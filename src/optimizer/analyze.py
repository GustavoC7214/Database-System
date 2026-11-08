"""Collect table statistics using Module 2 execution operators."""

import json
import tempfile
from contextlib import ExitStack
from pathlib import Path

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.seq_scan import SeqScan
from src.execution.sort import Sort
from src.optimizer.histogram import build_column_statistics
from src.optimizer.statistics import (
    ColumnStatistics,
    StatisticsStore,
    TableStatistics,
)
from src.storage.catalog import Catalog
from src.storage.directory_page import NO_NEXT_PAGE, DirectoryPage
from src.storage.disk_manager import DiskManager
from src.storage.record_codec import encode_record


class ColumnFileScan(Operator):
    """Read a disk-backed stream of individual column values."""

    def __init__(self, path: Path, column_type: str) -> None:
        super().__init__()
        self.path = path
        self.column_type = column_type
        self._file = None

    def open(self) -> None:
        self.close()
        self.schema = [("value", self.column_type)]
        self._file = self.path.open("r", encoding="utf-8")
        self._counters.tuples_out = 0
        self._counters.page_reads = 0
        self._counters.page_writes = 0
        self._counters.comparisons = 0

    def next(self) -> tuple[int | str, ...] | None:
        if self._file is None:
            raise RuntimeError("ColumnFileScan is not open")

        line = self._file.readline()
        if not line:
            return None

        value = json.loads(line)
        self._counters.tuples_out += 1
        return (value,)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def count_data_pages(table_path: Path) -> int:
    """Count registered data pages, excluding directory pages."""
    disk = DiskManager(table_path)
    directory_id = 0
    count = 0
    visited: set[int] = set()

    while directory_id != NO_NEXT_PAGE:
        if directory_id in visited:
            raise ValueError("Cycle detected in table directory pages")

        visited.add(directory_id)
        directory = DirectoryPage(
            directory_id,
            disk.read_page(directory_id),
        )

        count += directory.entry_count
        directory_id = directory.next_dir_page

    return count


def analyze_table(
    db_dir: str | Path,
    table: str,
    *,
    buckets: int = 20,
    frames: int = 32,
) -> TableStatistics:
    """Analyze one table and persist its statistics.

    The base table is scanned exactly once. Per-column temporary
    streams are externally sorted after the base scan completes.
    """
    if buckets < 1:
        raise ValueError("Bucket count must be at least 1")
    if frames < 4:
        raise ValueError("ANALYZE requires at least 4 frames")

    db_path = Path(db_dir)

    if not (db_path / "catalog.db").is_file():
        raise ValueError(f"Database catalog does not exist: {db_path}")

    catalog = Catalog(db_path, frames=frames)
    metadata = catalog.get_table(table)

    pages = SharedPageManager(frames)
    scan = SeqScan(db_path, table, pages)

    n_tuples = 0
    total_width = 0

    with tempfile.TemporaryDirectory(prefix="optimizer_analyze_") as temp:
        temp_path = Path(temp)
        column_files = [
            temp_path / f"column_{index}.jsonl" for index in range(len(metadata.schema))
        ]

        with ExitStack() as stack:
            writers = [
                stack.enter_context(path.open("w", encoding="utf-8"))
                for path in column_files
            ]

            scan.open()
            try:
                while (row := scan.next()) is not None:
                    n_tuples += 1
                    total_width += len(encode_record(row, metadata.schema))

                    for value, writer in zip(row, writers, strict=True):
                        writer.write(
                            json.dumps(
                                value,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                        writer.write("\n")
            finally:
                scan.close()

        columns: dict[str, ColumnStatistics] = {}

        for index, (name, column_type) in enumerate(metadata.schema):
            child = ColumnFileScan(column_files[index], column_type)
            sorter = Sort(
                child,
                keys=[("value", "ASC")],
                pages=pages,
            )

            sorter.open()
            try:

                def sorted_values(active_sorter=sorter):
                    while (row := active_sorter.next()) is not None:
                        yield row[0]

                columns[name] = build_column_statistics(
                    sorted_values(),
                    n_tuples=n_tuples,
                    buckets=buckets,
                )
            finally:
                sorter.close()

    statistics = TableStatistics(
        table=table,
        n_tuples=n_tuples,
        n_pages=count_data_pages(db_path / metadata.filename),
        width=total_width / n_tuples if n_tuples else 0.0,
        columns=columns,
    )

    StatisticsStore(db_path).save(statistics)
    return statistics
