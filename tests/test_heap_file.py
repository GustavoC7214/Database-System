import pytest

from src.storage.directory_page import NO_NEXT_PAGE, DirectoryPage
from src.storage.disk_manager import PAGE_SIZE, DiskManager
from src.storage.heap_file import HeapFile
from src.storage.slotted_page import SlottedPage


def test_heap_file_creates_directory_page(tmp_path):
    path = tmp_path / "R.db"

    heap = HeapFile(path)

    assert path.exists()
    assert heap.page_count == 1
    assert path.stat().st_size == PAGE_SIZE


def test_page_zero_is_directory_page(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    data = heap.disk.read_page(0)
    directory = DirectoryPage(0, data)

    assert directory.page_id == 0
    assert directory.next_dir_page == NO_NEXT_PAGE
    assert directory.entry_count == 0


def test_reopen_heap_file(tmp_path):
    path = tmp_path / "R.db"

    first = HeapFile(path)
    second = HeapFile(path)

    assert first.page_count == 1
    assert second.page_count == 1


def test_reopen_preserves_directory_entries(tmp_path):
    path = tmp_path / "R.db"

    heap = HeapFile(path)

    directory = DirectoryPage(0, heap.disk.read_page(0))
    directory.add_entry(1, 4088)

    heap.disk.write_page(0, directory.to_bytes())

    reopened = HeapFile(path)
    restored = DirectoryPage(0, reopened.disk.read_page(0))

    assert restored.entry_count == 1
    assert restored.get_entry(0) == (1, 4088)


def test_heap_file_uses_existing_database_file(tmp_path):
    path = tmp_path / "R.db"

    disk = DiskManager(path)
    disk.allocate_page()
    disk.write_page(0, DirectoryPage(0).to_bytes())

    heap = HeapFile(path)

    assert heap.page_count == 1
    assert heap.disk.read_page(0) == DirectoryPage(0).to_bytes()


def test_insert_first_record(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    rid = heap.insert(b"hello")

    assert rid == (1, 0)
    assert heap.page_count == 2
    assert heap.get(rid) == b"hello"


def test_multiple_records_same_page(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    first = heap.insert(b"first")
    second = heap.insert(b"second")
    third = heap.insert(b"third")

    assert first == (1, 0)
    assert second == (1, 1)
    assert third == (1, 2)
    assert heap.page_count == 2

    assert heap.get(first) == b"first"
    assert heap.get(second) == b"second"
    assert heap.get(third) == b"third"


def test_directory_free_space_updated(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    heap.insert(b"A" * 13)
    heap.flush()

    directory = DirectoryPage(0, heap.disk.read_page(0))

    assert directory.entry_count == 1
    assert directory.get_entry(0) == (1, 4071)


def test_allocate_new_data_page_when_full(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    for _ in range(240):
        heap.insert(b"A" * 13)

    rid = heap.insert(b"B" * 13)

    assert rid == (2, 0)
    assert heap.page_count == 3

    heap.flush()

    directory = DirectoryPage(0, heap.disk.read_page(0))

    assert directory.entry_count == 2
    assert directory.get_entry(0) == (1, 8)
    assert directory.get_entry(1) == (2, 4071)


def test_first_fit_uses_earliest_available_page(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    for _ in range(240):
        heap.insert(b"A" * 13)

    heap.insert(b"B" * 13)

    # Page 1 has 8 free bytes, enough for a 4-byte record
    # plus its 4-byte slot directory entry.
    rid = heap.insert(b"CCCC")

    assert rid == (1, 240)
    assert heap.get(rid) == b"CCCC"


def test_records_persist_after_reopening(tmp_path):
    path = tmp_path / "R.db"

    heap = HeapFile(path)
    first = heap.insert(b"hello")
    second = heap.insert(b"world")
    heap.flush()

    reopened = HeapFile(path)

    assert reopened.get(first) == b"hello"
    assert reopened.get(second) == b"world"


def test_oversized_record_rejected(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    with pytest.raises(ValueError, match="too large"):
        heap.insert(b"A" * 4085)

    assert heap.page_count == 1


def test_invalid_rid_rejected(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    heap.insert(b"hello")

    with pytest.raises(ValueError):
        heap.get((1, 99))


def test_directory_chaining(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    for _ in range(682):
        heap.insert(b"A" * 4084)

    heap.flush()

    first_directory = DirectoryPage(0, heap.disk.read_page(0))

    assert first_directory.entry_count == 681
    assert first_directory.next_dir_page != NO_NEXT_PAGE

    second_directory_id = first_directory.next_dir_page
    second_directory = DirectoryPage(
        second_directory_id,
        heap.disk.read_page(second_directory_id),
    )

    assert second_directory.entry_count == 1
    assert second_directory.next_dir_page == NO_NEXT_PAGE
    assert heap.page_count == 684


def test_delete_record(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    rid = heap.insert(b"hello")

    heap.delete(rid)
    heap.flush()

    page = SlottedPage(1, heap.disk.read_page(1))
    assert page.get_slot(0) == (0, 0)

    with pytest.raises(ValueError, match="deleted"):
        heap.get(rid)


def test_delete_preserves_other_records(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    first = heap.insert(b"Alice")
    second = heap.insert(b"Bob")
    third = heap.insert(b"Charlie")

    heap.delete(second)

    assert heap.get(first) == b"Alice"
    assert heap.get(third) == b"Charlie"


def test_double_delete_rejected(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    rid = heap.insert(b"hello")

    heap.delete(rid)

    with pytest.raises(ValueError, match="already deleted"):
        heap.delete(rid)


def test_deleted_slot_not_reused(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    first = heap.insert(b"first")
    heap.insert(b"second")

    heap.delete(first)

    third = heap.insert(b"third")

    assert third == (1, 2)


def test_delete_does_not_reclaim_space(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    rid = heap.insert(b"A" * 100)
    heap.flush()

    before = DirectoryPage(0, heap.disk.read_page(0))
    free_before = before.get_entry(0)[1]

    heap.delete(rid)
    heap.flush()

    after = DirectoryPage(0, heap.disk.read_page(0))
    free_after = after.get_entry(0)[1]

    assert free_before == free_after
    assert free_after == 3984


def test_deletion_persists_after_reopening(tmp_path):
    path = tmp_path / "R.db"

    heap = HeapFile(path)
    rid = heap.insert(b"hello")
    heap.delete(rid)
    heap.flush()

    reopened = HeapFile(path)

    with pytest.raises(ValueError, match="deleted"):
        reopened.get(rid)


def test_scan_empty_heap(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    assert list(heap.scan()) == []


def test_scan_single_record(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    rid = heap.insert(b"hello")

    assert list(heap.scan()) == [(rid, b"hello")]


def test_scan_multiple_records(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    first = heap.insert(b"Alice")
    second = heap.insert(b"Bob")
    third = heap.insert(b"Charlie")

    assert list(heap.scan()) == [
        (first, b"Alice"),
        (second, b"Bob"),
        (third, b"Charlie"),
    ]


def test_scan_skips_deleted_records(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    first = heap.insert(b"Alice")
    second = heap.insert(b"Bob")
    third = heap.insert(b"Charlie")

    heap.delete(second)

    assert list(heap.scan()) == [
        (first, b"Alice"),
        (third, b"Charlie"),
    ]


def test_scan_multiple_data_pages(tmp_path):
    heap = HeapFile(tmp_path / "R.db")

    expected = []

    for index in range(250):
        record = f"record-{index}".encode().ljust(100, b" ")
        rid = heap.insert(record)
        expected.append((rid, record))

    assert heap.page_count > 2
    assert list(heap.scan()) == expected


def test_scan_is_lazy(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    heap.insert(b"first")
    heap.insert(b"second")

    iterator = heap.scan()

    # Creating the generator should not execute its body.
    assert hasattr(iterator, "__next__")

    assert next(iterator) == ((1, 0), b"first")
    assert next(iterator) == ((1, 1), b"second")

    with pytest.raises(StopIteration):
        next(iterator)


def test_scan_with_one_buffer_frame(tmp_path):
    heap = HeapFile(tmp_path / "R.db", frames=1)

    records = [b"Alice", b"Bob", b"Charlie"]
    rids = [heap.insert(record) for record in records]

    assert list(heap.scan()) == list(zip(rids, records))


def test_scan_with_two_buffer_frames(tmp_path):
    heap = HeapFile(tmp_path / "R.db", frames=2)

    records = [bytes([i % 256]) * 1000 for i in range(20)]
    rids = [heap.insert(record) for record in records]

    assert list(heap.scan()) == list(zip(rids, records))


def test_scan_early_termination_releases_pins(tmp_path):
    heap = HeapFile(tmp_path / "R.db", frames=1)

    heap.insert(b"Alice")
    heap.insert(b"Bob")

    iterator = heap.scan()
    next(iterator)

    assert all(frame.pin_count == 0 for frame in heap.buffer.frames)

    # Scanning must remain possible even if the iterator is not exhausted.
    assert len(list(heap.scan())) == 2


def test_scan_sees_cached_deletions(tmp_path):
    heap = HeapFile(tmp_path / "R.db", frames=2)

    first = heap.insert(b"Alice")
    second = heap.insert(b"Bob")

    heap.delete(first)

    assert list(heap.scan()) == [(second, b"Bob")]


def test_heap_file_explicit_flush(tmp_path):
    path = tmp_path / "R.db"
    heap = HeapFile(path)

    rid = heap.insert(b"Alice")
    heap.flush()

    reopened = HeapFile(path)

    assert reopened.get(rid) == b"Alice"


def test_insert_keeps_dirty_pages_cached_until_flush(tmp_path):
    heap = HeapFile(tmp_path / "R.db", frames=8)

    rid = heap.insert(b"Alice")

    # The record must be immediately readable through the Buffer Pool.
    assert heap.get(rid) == b"Alice"

    # With enough frames, insertion should not force a disk write.
    assert heap.buffer.stats()["writes"] == 1

    # The new data page should still be dirty in the Buffer Pool.
    frame = heap.buffer.frames[heap.buffer.page_table[rid[0]]]
    assert frame.dirty is True

    # Explicit flushing persists the changes.
    heap.flush()

    assert frame.dirty is False
    assert heap.disk.read_page(rid[0])[:4] == rid[0].to_bytes(4, byteorder="little")


def test_rid_cannot_reference_directory_page(tmp_path):
    heap = HeapFile(tmp_path / "R.db")
    heap.insert(b"hello")

    with pytest.raises(ValueError, match="Invalid record page"):
        heap.get((0, 0))

    with pytest.raises(ValueError, match="Invalid record page"):
        heap.delete((0, 0))
