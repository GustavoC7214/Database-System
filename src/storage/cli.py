"""Command-line interface for the storage engine."""

import argparse
import json
from pathlib import Path

from src.storage.catalog import Catalog
from src.storage.csv_loader import load_csv
from src.storage.directory_page import NO_NEXT_PAGE, DirectoryPage
from src.storage.disk_manager import DiskManager
from src.storage.heap_file import HeapFile
from src.storage.record_codec import decode_record
from src.storage.slotted_page import SlottedPage
from src.storage.trace_runner import run_trace


def build_parser() -> argparse.ArgumentParser:
    """Build the storage CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="storage",
        description="Storage engine and buffer pool CLI",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    create_table = commands.add_parser(
        "create-table",
        help="Create a new table",
    )

    create_table.add_argument(
        "--db",
        required=True,
        help="Database directory",
    )
    create_table.add_argument(
        "--name",
        required=True,
        help="Table name",
    )
    create_table.add_argument(
        "--schema",
        required=True,
        help="Column definitions",
    )

    load = commands.add_parser(
        "load",
        help="Load CSV records into an existing table",
    )

    load.add_argument(
        "--db",
        required=True,
        help="Database directory",
    )
    load.add_argument(
        "--table",
        required=True,
        help="Existing table name",
    )
    load.add_argument(
        "--file",
        required=True,
        help="Path to a headerless CSV file",
    )

    scan = commands.add_parser(
        "scan",
        help="Scan records from an existing table",
    )

    scan.add_argument(
        "--db",
        required=True,
        help="Database directory",
    )
    scan.add_argument(
        "--table",
        required=True,
        help="Existing table name",
    )
    scan.add_argument(
        "--frames",
        type=int,
        default=8,
        help="Number of buffer pool frames",
    )
    scan.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to display",
    )
    scan.add_argument(
        "--json",
        action="store_true",
        help="Output records as JSON",
    )

    layout = commands.add_parser(
        "layout",
        help="Inspect the internal layout of a data page",
    )

    layout.add_argument(
        "--db",
        required=True,
        help="Database directory",
    )
    layout.add_argument(
        "--table",
        required=True,
        help="Existing table name",
    )
    layout.add_argument(
        "--page",
        type=int,
        required=True,
        help="Zero-based data page ID",
    )

    trace = commands.add_parser(
        "trace",
        help="Replay page accesses through the buffer pool",
    )

    trace.add_argument(
        "--db",
        required=True,
        help="Database directory",
    )
    trace.add_argument(
        "--file",
        required=True,
        help="Path to the page access trace",
    )
    trace.add_argument(
        "--frames",
        type=int,
        default=16,
        help="Number of buffer pool frames",
    )
    trace.add_argument(
        "--policy",
        choices=["lru", "clock"],
        default="lru",
        help="Buffer replacement policy",
    )
    trace.add_argument(
        "--json",
        action="store_true",
        help="Output buffer pool statistics as JSON",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute a storage CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-table":
        catalog = Catalog(args.db)
        metadata = catalog.create_table(
            args.name,
            args.schema,
        )

        print(f"Created table: {metadata.name}")
        print(f"Schema: {metadata.schema}")
        print(f"File: {metadata.filename}")

    elif args.command == "load":
        inserted_count = load_csv(
            db_dir=args.db,
            table_name=args.table,
            csv_path=args.file,
        )

        print(f"Loaded {inserted_count} records into table {args.table}")

    elif args.command == "scan":
        if args.frames < 1:
            parser.error("--frames must be at least 1")

        if args.limit is not None and args.limit < 0:
            parser.error("--limit cannot be negative")

        catalog = Catalog(args.db, frames=args.frames)
        metadata = catalog.get_table(args.table)

        heap = HeapFile(
            Path(args.db) / metadata.filename,
            frames=args.frames,
        )

        records = []

        if args.limit != 0:
            for _, data in heap.scan():
                values = decode_record(data, metadata.schema)
                records.append(
                    dict(
                        zip(
                            (name for name, _ in metadata.schema),
                            values,
                        )
                    )
                )

                if args.limit is not None and len(records) >= args.limit:
                    break

        if args.json:
            print(json.dumps(records, ensure_ascii=False))
        else:
            for record in records:
                print(record)

    elif args.command == "layout":
        catalog = Catalog(args.db)
        metadata = catalog.get_table(args.table)

        disk = DiskManager(Path(args.db) / metadata.filename)

        if args.page < 1 or args.page >= disk.page_count():
            parser.error(
                f"Invalid data page ID {args.page}; "
                f"file contains {disk.page_count()} pages"
            )

        directory_page_id = 0
        is_data_page = False

        while directory_page_id != NO_NEXT_PAGE:
            directory = DirectoryPage(
                directory_page_id,
                disk.read_page(directory_page_id),
            )

            for index in range(directory.entry_count):
                data_page_id, _ = directory.get_entry(index)

                if data_page_id == args.page:
                    is_data_page = True
                    break

            if is_data_page:
                break

            directory_page_id = directory.next_dir_page

        if not is_data_page:
            parser.error(f"Page {args.page} is not a registered data page")

        page = SlottedPage(
            args.page,
            disk.read_page(args.page),
        )

        print(f"Table: {args.table}")
        print(f"Page ID: {page.page_id}")
        print(f"Slot count: {page.slot_count}")
        print(f"Free end: {page.free_end}")
        print(f"Free space: {page.free_space}")

        for slot_number in range(page.slot_count):
            offset, length = page.get_slot(slot_number)

            if length == 0:
                print(f"Slot {slot_number}: DEAD")
            else:
                print(f"Slot {slot_number}: offset={offset}, length={length}")

    elif args.command == "trace":
        if args.frames < 1:
            parser.error("--frames must be at least 1")

        stats = run_trace(
            db_dir=args.db,
            trace_path=args.file,
            frames=args.frames,
            policy=args.policy,
        )

        if args.json:
            print(json.dumps(stats))
        else:
            print(f"Replacement policy: {args.policy.upper()}")
            print(f"Buffer frames: {args.frames}")
            print(f"Hits: {stats['hits']}")
            print(f"Misses: {stats['misses']}")
            print(f"Evictions: {stats['evictions']}")
            print(f"Disk reads: {stats['reads']}")
            print(f"Disk writes: {stats['writes']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
