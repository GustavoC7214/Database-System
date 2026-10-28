from src.execution.filter import Filter
from src.execution.page_manager import SharedPageManager
from src.execution.project import Project
from src.execution.seq_scan import SeqScan
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def test_seq_scan_reads_real_table(tmp_path):
    # Create a table using Module 1.
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "R",
        "id:INT,name:VARCHAR(20)",
    )

    # Insert three records.
    heap = HeapFile(tmp_path / metadata.filename)

    rows = [
        (1, "Alice"),
        (2, "Bob"),
        (3, "Charlie"),
    ]

    for row in rows:
        heap.insert(encode_record(row, metadata.schema))

    heap.flush()

    # Execute the scan using Module 2's shared page manager.
    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "R", pages)

    scan.open()

    assert scan.schema == [
        ("R.id", "INT"),
        ("R.name", "VARCHAR(20)"),
    ]

    actual = []

    while (row := scan.next()) is not None:
        actual.append(row)

    scan.close()

    assert actual == rows
    assert scan.counters()["tuples_out"] == 3
    assert scan.counters()["page_reads"] == 4

    # Closing the scan must release every page pin.
    assert all(count == 0 for count in pages.pin_counts)


def test_seq_scan_early_close_releases_pins(tmp_path):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table("R", "id:INT")

    heap = HeapFile(tmp_path / metadata.filename)

    for value in range(10):
        heap.insert(encode_record((value,), metadata.schema))

    heap.flush()

    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "R", pages)

    scan.open()

    # Read only one tuple, leaving the scan unfinished.
    assert scan.next() == (0,)

    # The scan may still be holding a pinned data page.
    assert any(count > 0 for count in pages.pin_counts)

    scan.close()

    # Closing early must release every pin.
    assert all(count == 0 for count in pages.pin_counts)

    assert scan.counters()["tuples_out"] == 1


def test_filter_project_pipeline(tmp_path):
    # Create the database table.
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "R",
        "id:INT,name:VARCHAR(20)",
    )

    heap = HeapFile(tmp_path / metadata.filename)

    rows = [
        (1, "Alice"),
        (2, "Bob"),
        (3, "Charlie"),
        (4, "David"),
    ]

    for row in rows:
        heap.insert(encode_record(row, metadata.schema))

    heap.flush()

    # Build the execution pipeline.
    pages = SharedPageManager(frames=4)

    scan = SeqScan(tmp_path, "R", pages)
    filtered = Filter(scan, "R.id", ">", 1)
    projected = Project(filtered, ["R.name"])

    # Execute the query.
    projected.open()

    assert projected.schema == [
        ("R.name", "VARCHAR(20)"),
    ]

    results = []

    while (row := projected.next()) is not None:
        results.append(row)

    projected.close()

    # Verify the results.
    assert results == [
        ("Bob",),
        ("Charlie",),
        ("David",),
    ]

    # Verify operator counters.
    assert scan.counters()["tuples_out"] == 4
    assert filtered.counters()["comparisons"] == 4
    assert filtered.counters()["tuples_out"] == 3
    assert projected.counters()["tuples_out"] == 3

    # All page pins must be released.
    assert all(count == 0 for count in pages.pin_counts)
