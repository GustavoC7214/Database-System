from src.execution.page_manager import SharedPageManager
from src.execution.seq_scan import SeqScan
from src.execution.sort import Sort
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def test_sort_real_table_multiple_keys(tmp_path):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "R",
        "id:INT,name:VARCHAR(20)",
    )

    rows = [
        (3, "Bob"),
        (1, "Alice"),
        (4, "Bob"),
        (2, "Charlie"),
        (5, "Alice"),
        (6, "Bob"),
    ]

    heap = HeapFile(tmp_path / metadata.filename)

    for row in rows:
        heap.insert(encode_record(row, metadata.schema))

    heap.flush()

    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "R", pages)

    sort = Sort(
        child=scan,
        keys=[
            ("R.name", "ASC"),
            ("R.id", "DESC"),
        ],
        pages=pages,
    )

    sort.open()

    assert sort.schema == [
        ("R.id", "INT"),
        ("R.name", "VARCHAR(20)"),
    ]

    result = []

    while (row := sort.next()) is not None:
        result.append(row)

    sort.close()

    assert result == [
        (5, "Alice"),
        (1, "Alice"),
        (6, "Bob"),
        (4, "Bob"),
        (3, "Bob"),
        (2, "Charlie"),
    ]

    assert sort.counters()["tuples_out"] == 6
    assert all(pin == 0 for pin in pages.pin_counts)


def test_sort_multiple_merge_passes(tmp_path):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "LargeR",
        "id:INT,payload:VARCHAR(200)",
    )

    # Large enough to force multiple initial runs with B = 4.
    rows = [(value, "x" * 150) for value in range(500, 0, -1)]

    heap = HeapFile(tmp_path / metadata.filename)

    for row in rows:
        heap.insert(encode_record(row, metadata.schema))

    heap.flush()

    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "LargeR", pages)

    sort = Sort(
        child=scan,
        keys=[("LargeR.id", "ASC")],
        pages=pages,
    )

    sort.open()

    result = []

    while (row := sort.next()) is not None:
        result.append(row)

    sort.close()

    assert result == sorted(rows, key=lambda row: row[0])
    assert len(result) == 500

    assert scan.counters()["tuples_out"] == 500

    stats = sort.counters()

    assert stats["tuples_out"] == 500
    assert stats["page_reads"] > 0
    assert stats["page_writes"] > 0
    print(
        f"\nExternal Sort I/O: "
        f"reads={stats['page_reads']}, "
        f"writes={stats['page_writes']}"
    )

    assert all(pin == 0 for pin in pages.pin_counts)


def test_sort_releases_frames_when_closed_early(tmp_path):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(
        "EarlyClose",
        "id:INT,payload:VARCHAR(200)",
    )

    heap = HeapFile(tmp_path / metadata.filename)

    for value in range(500, 0, -1):
        heap.insert(
            encode_record(
                (value, "x" * 150),
                metadata.schema,
            )
        )

    heap.flush()

    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "EarlyClose", pages)

    sort = Sort(
        child=scan,
        keys=[("EarlyClose.id", "ASC")],
        pages=pages,
    )

    sort.open()

    try:
        first_row = sort.next()

        assert first_row is not None
        assert first_row[0] == 1
        assert len(pages.reserved_frames) > 0
    finally:
        sort.close()

    assert pages.reserved_frames == set()


def test_sort_descending_string_prefixes(tmp_path):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table("Prefixes", "id:INT,name:VARCHAR(30)")
    rows = [(1, "a"), (2, "aa"), (3, "b"), (4, "aaa"), (5, "á")]
    heap = HeapFile(tmp_path / metadata.filename)
    for row in rows:
        heap.insert(encode_record(row, metadata.schema))
    heap.flush()

    pages = SharedPageManager(frames=4)
    sort = Sort(
        SeqScan(tmp_path, "Prefixes", pages), [("Prefixes.name", "DESC")], pages
    )
    sort.open()
    try:
        actual = []
        while (row := sort.next()) is not None:
            actual.append(row)
    finally:
        sort.close()

    assert actual == sorted(rows, key=lambda row: row[1].encode("utf-8"), reverse=True)
    assert pages.reserved_frames == set()
