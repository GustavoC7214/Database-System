from src.execution.distinct import Distinct
from src.execution.page_manager import SharedPageManager
from src.execution.seq_scan import SeqScan
from src.execution.union import Union
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def table(root, name, rows):
    catalog = Catalog(root)
    metadata = catalog.create_table(name, "id:INT,label:VARCHAR(200)")

    heap = HeapFile(root / metadata.filename)

    for row in rows:
        heap.insert(encode_record(row, metadata.schema))

    heap.flush()


def drain(operator):
    operator.open()

    try:
        rows = []

        while (row := operator.next()) is not None:
            rows.append(row)

        return rows

    finally:
        operator.close()


def test_distinct_external_large_and_reopen(tmp_path):
    values = [(i % 17, "x" * 150) for i in range(600)]

    table(tmp_path, "R", values)

    pages = SharedPageManager(4)

    operator = Distinct(SeqScan(tmp_path, "R", pages), pages)

    for _ in range(2):
        result = drain(operator)

        assert result == [(i, "x" * 150) for i in range(17)]

        assert operator.counters()["tuples_out"] == 17
        assert all(count == 0 for count in pages.pin_counts)
        assert not pages.reserved_frames


def test_union_set_semantics(tmp_path):
    table(
        tmp_path,
        "R",
        [
            (1, "a"),
            (1, "a"),
            (2, "b"),
        ],
    )

    table(
        tmp_path,
        "S",
        [
            (2, "b"),
            (3, "c"),
            (3, "c"),
        ],
    )

    pages = SharedPageManager(4)

    op = Union(SeqScan(tmp_path, "R", pages), SeqScan(tmp_path, "S", pages), pages)

    assert drain(op) == [
        (1, "a"),
        (2, "b"),
        (3, "c"),
    ]

    assert all(count == 0 for count in pages.pin_counts)


def test_distinct_empty(tmp_path):
    table(tmp_path, "R", [])

    pages = SharedPageManager(4)

    assert drain(Distinct(SeqScan(tmp_path, "R", pages), pages)) == []


def test_distinct_opens_child_once(tmp_path, monkeypatch):
    table(tmp_path, "R", [(1, "a"), (1, "a"), (2, "b")])

    pages = SharedPageManager(4)
    child = SeqScan(tmp_path, "R", pages)

    open_calls = 0
    original_open = child.open

    def tracked_open():
        nonlocal open_calls
        open_calls += 1
        original_open()

    monkeypatch.setattr(child, "open", tracked_open)

    operator = Distinct(child, pages)

    assert drain(operator) == [(1, "a"), (2, "b")]
    assert open_calls == 1
    assert all(count == 0 for count in pages.pin_counts)
    assert not pages.reserved_frames


def test_distinct_opens_child_once_per_reexecution(tmp_path, monkeypatch):
    table(tmp_path, "R", [(1, "a"), (2, "b"), (1, "a")])

    pages = SharedPageManager(4)
    child = SeqScan(tmp_path, "R", pages)

    open_calls = 0
    original_open = child.open

    def tracked_open():
        nonlocal open_calls
        open_calls += 1
        original_open()

    monkeypatch.setattr(child, "open", tracked_open)

    operator = Distinct(child, pages)

    for expected_calls in (1, 2):
        assert drain(operator) == [(1, "a"), (2, "b")]
        assert open_calls == expected_calls
        assert all(count == 0 for count in pages.pin_counts)
        assert not pages.reserved_frames


def test_distinct_counters_survive_close(tmp_path):
    values = [(i % 17, "x" * 150) for i in range(600)]
    table(tmp_path, "R", values)

    pages = SharedPageManager(4)
    operator = Distinct(SeqScan(tmp_path, "R", pages), pages)

    operator.open()

    try:
        rows = []
        while (row := operator.next()) is not None:
            rows.append(row)

        before_close = operator.counters()
    finally:
        operator.close()

    after_close = operator.counters()

    assert len(rows) == 17
    assert before_close["tuples_out"] == 17
    assert before_close["page_reads"] > 0
    assert before_close["page_writes"] > 0
    assert after_close == before_close

    assert all(count == 0 for count in pages.pin_counts)
    assert not pages.reserved_frames


def test_distinct_counters_reset_on_reopen(tmp_path):
    table(
        tmp_path,
        "R",
        [(i % 5, "x" * 150) for i in range(600)],
    )

    pages = SharedPageManager(4)
    operator = Distinct(SeqScan(tmp_path, "R", pages), pages)

    first_result = drain(operator)
    first_counters = operator.counters()

    second_result = drain(operator)
    second_counters = operator.counters()

    assert first_result == second_result
    assert len(first_result) == 5
    assert first_counters == second_counters

    assert all(count == 0 for count in pages.pin_counts)
    assert not pages.reserved_frames


def test_hash_distinct_small(tmp_path):
    table(
        tmp_path,
        "R",
        [
            (1, "a"),
            (1, "a"),
            (2, "b"),
            (3, "c"),
            (2, "b"),
        ],
    )

    pages = SharedPageManager(4)
    op = Distinct(SeqScan(tmp_path, "R", pages), pages, mode="hash")

    assert set(drain(op)) == {
        (1, "a"),
        (2, "b"),
        (3, "c"),
    }
    assert op.counters()["tuples_out"] == 3
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)


def test_hash_distinct_large(tmp_path):
    table(tmp_path, "R", [(i % 101, "x" * 150) for i in range(1200)])

    pages = SharedPageManager(4)
    op = Distinct(SeqScan(tmp_path, "R", pages), pages, mode="hash")

    assert set(drain(op)) == {(i, "x" * 150) for i in range(101)}

    counts = op.counters()
    assert counts["tuples_out"] == 101
    assert counts["page_reads"] > 0
    assert counts["page_writes"] > 0
    assert not pages.reserved_frames


def test_hash_distinct_heavy_skew(tmp_path):
    table(tmp_path, "R", [(7, "repeated" * 20) for _ in range(1000)])

    pages = SharedPageManager(4)
    op = Distinct(SeqScan(tmp_path, "R", pages), pages, mode="hash")

    assert drain(op) == [(7, "repeated" * 20)]
    assert not pages.reserved_frames


def test_hash_distinct_empty(tmp_path):
    table(tmp_path, "R", [])

    pages = SharedPageManager(4)
    op = Distinct(SeqScan(tmp_path, "R", pages), pages, mode="hash")

    assert drain(op) == []
    assert op.counters()["tuples_out"] == 0
    assert not pages.reserved_frames


def test_hash_distinct_reopen_and_counters(tmp_path):
    table(tmp_path, "R", [(i % 17, "value" * 30) for i in range(500)])

    pages = SharedPageManager(4)
    op = Distinct(SeqScan(tmp_path, "R", pages), pages, mode="hash")

    first = set(drain(op))
    first_counts = op.counters()

    second = set(drain(op))
    second_counts = op.counters()

    assert first == second
    assert len(first) == 17
    assert first_counts == second_counts
    assert not pages.reserved_frames


def test_hash_distinct_partition_overflow(tmp_path):
    from src.execution.hash_distinct import HashDistinct

    # Force all unique rows into the same hash partition.
    original_partition_index = HashDistinct._partition_index
    HashDistinct._partition_index = staticmethod(lambda row, count: 0)

    try:
        values = [(i, f"value_{i:05d}" + "x" * 150) for i in range(500)]
        table(tmp_path, "R", values)

        pages = SharedPageManager(4)
        op = Distinct(
            SeqScan(tmp_path, "R", pages),
            pages,
            mode="hash",
        )

        result = drain(op)

        assert len(result) == 500
        assert set(result) == set(values)
        assert op.counters()["tuples_out"] == 500
        assert op.counters()["page_reads"] > 0
        assert op.counters()["page_writes"] > 0
        assert not pages.reserved_frames
        assert all(count == 0 for count in pages.pin_counts)
    finally:
        HashDistinct._partition_index = staticmethod(original_partition_index)


def test_hash_distinct_overflow_shared_frame_limit(
    tmp_path,
    monkeypatch,
):
    from src.execution.hash_distinct import HashDistinct

    values = [(i, f"value_{i:05d}" + "x" * 150) for i in range(500)]
    table(tmp_path, "R", values)

    pages = SharedPageManager(4)
    peak_reserved = 0

    original_reserve = pages.reserve_frames

    def tracked_reserve(count):
        nonlocal peak_reserved
        indices = original_reserve(count)
        peak_reserved = max(
            peak_reserved,
            len(pages.reserved_frames),
        )
        return indices

    monkeypatch.setattr(pages, "reserve_frames", tracked_reserve)
    monkeypatch.setattr(
        HashDistinct,
        "_partition_index",
        staticmethod(lambda row, count: 0),
    )

    op = Distinct(
        SeqScan(tmp_path, "R", pages),
        pages,
        mode="hash",
    )

    result = drain(op)

    assert set(result) == set(values)
    assert len(result) == 500

    assert peak_reserved <= pages.capacity
    assert not pages.reserved_frames
    assert all(count == 0 for count in pages.pin_counts)
