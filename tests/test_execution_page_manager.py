from pathlib import Path

import pytest

from src.execution.page import PageKey
from src.execution.page_manager import SharedPageManager
from src.storage.disk_manager import PAGE_SIZE, DiskManager


def test_initial_capacity():
    manager = SharedPageManager(4)

    assert manager.capacity == 4
    assert len(manager.frames) == 4


def test_frame_sizes():
    manager = SharedPageManager(8)

    assert all(len(frame) == PAGE_SIZE for frame in manager.frames)


def test_frames_are_independent():
    manager = SharedPageManager(4)

    manager.frames[0][0] = 42

    assert manager.frames[0][0] == 42
    assert manager.frames[1][0] == 0


def test_initial_page_table():
    manager = SharedPageManager(4)

    assert manager.page_table == {}


def test_initial_statistics():
    manager = SharedPageManager(4)

    assert manager.stats() == {
        "hits": 0,
        "reads": 0,
        "writes": 0,
    }


def test_invalid_frame_count():
    with pytest.raises(ValueError, match="at least 4 frames"):
        SharedPageManager(3)


def test_read_page(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    expected = bytes([42]) * PAGE_SIZE
    disk.write_page(0, expected)

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    # First access: physical disk read.
    result = manager.read_page(key)

    assert result == expected
    assert manager.stats()["reads"] == 1
    assert manager.stats()["hits"] == 0

    # Second access: cached page.
    result = manager.read_page(key)

    assert result == expected
    assert manager.stats()["reads"] == 1
    assert manager.stats()["hits"] == 1

    # The page occupies one shared frame.
    assert len(manager.page_table) == 1


def test_cache_capacity(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(5):
        disk.write_page(
            page_id,
            bytes([page_id]) * PAGE_SIZE,
        )

    manager = SharedPageManager(4)

    # Fill all four frames.
    for page_id in range(4):
        manager.read_page(PageKey(file_path, page_id))

    assert len(manager.page_table) == 4
    assert manager.stats()["reads"] == 4

    # Reading a fifth page evicts the oldest cached page.
    result = manager.read_page(PageKey(file_path, 4))

    assert result == bytes([4]) * PAGE_SIZE
    assert len(manager.page_table) == 4
    assert PageKey(file_path, 0) not in manager.page_table
    assert PageKey(file_path, 4) in manager.page_table
    assert manager.stats()["reads"] == 5

    # Accessing the evicted page requires another disk read.
    result = manager.read_page(PageKey(file_path, 0))

    assert result == bytes([0]) * PAGE_SIZE
    assert manager.stats()["reads"] == 6


def test_initial_pin_counts():
    manager = SharedPageManager(4)

    assert manager.pin_counts == [0, 0, 0, 0]
    assert len(manager.pin_counts) == manager.capacity


def test_pin_cached_page(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)
    disk.write_page(0, bytes(PAGE_SIZE))

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    manager.read_page(key)
    manager.pin_page(key)

    frame_index = manager.page_table[key]

    assert manager.pin_counts[frame_index] == 1

    # Multiple users can pin the same page.
    manager.pin_page(key)

    assert manager.pin_counts[frame_index] == 2


def test_pin_uncached_page():
    manager = SharedPageManager(4)

    with pytest.raises(ValueError, match="Page is not cached"):
        manager.pin_page(PageKey(Path("R.db"), 0))


def test_unpin_cached_page(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)
    disk.write_page(0, bytes(PAGE_SIZE))

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    manager.read_page(key)
    manager.pin_page(key)
    manager.pin_page(key)

    frame_index = manager.page_table[key]

    assert manager.pin_counts[frame_index] == 2

    manager.unpin_page(key)
    assert manager.pin_counts[frame_index] == 1

    manager.unpin_page(key)
    assert manager.pin_counts[frame_index] == 0


def test_invalid_unpin(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)
    disk.write_page(0, bytes(PAGE_SIZE))

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    # Cannot unpin a page that is not cached.
    with pytest.raises(ValueError, match="Page is not cached"):
        manager.unpin_page(key)

    manager.read_page(key)

    # Cannot unpin a cached page with no active pins.
    with pytest.raises(ValueError, match="Page is not pinned"):
        manager.unpin_page(key)


def test_pinned_page_is_not_evicted(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(5):
        disk.write_page(
            page_id,
            bytes([page_id]) * PAGE_SIZE,
        )

    manager = SharedPageManager(4)

    # Fill the cache.
    for page_id in range(4):
        manager.read_page(PageKey(file_path, page_id))

    # Protect the first page.
    pinned_key = PageKey(file_path, 0)
    manager.pin_page(pinned_key)

    # Read a fifth page, forcing eviction.
    manager.read_page(PageKey(file_path, 4))

    # Page 0 must remain cached.
    assert pinned_key in manager.page_table

    # Page 1 should have been evicted instead.
    assert PageKey(file_path, 1) not in manager.page_table
    assert PageKey(file_path, 4) in manager.page_table

    # The pin count must remain unchanged.
    frame_index = manager.page_table[pinned_key]
    assert manager.pin_counts[frame_index] == 1


def test_all_frames_pinned(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(5):
        disk.write_page(
            page_id,
            bytes([page_id]) * PAGE_SIZE,
        )

    manager = SharedPageManager(4)

    # Fill and pin every frame.
    for page_id in range(4):
        key = PageKey(file_path, page_id)
        manager.read_page(key)
        manager.pin_page(key)

    # No frame is available for replacement.
    with pytest.raises(
        RuntimeError,
        match="All shared page frames are pinned",
    ):
        manager.read_page(PageKey(file_path, 4))

    # The existing cached pages must remain intact.
    assert len(manager.page_table) == 4
    assert all(count == 1 for count in manager.pin_counts)


def test_read_page_returns_readonly_view(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    expected = bytes([42]) * PAGE_SIZE
    disk.write_page(0, expected)

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    view = manager.read_page(key)

    # The returned object is a memoryview.
    assert isinstance(view, memoryview)

    # It contains the expected page data.
    assert view == expected

    # It is read-only.
    assert view.readonly

    with pytest.raises(TypeError):
        view[0] = 99

    # It references the existing frame rather than a copy.
    frame_index = manager.page_table[key]
    assert view.obj is manager.frames[frame_index]


def test_pinned_page_context_manager(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    expected = bytes([42]) * PAGE_SIZE
    disk.write_page(0, expected)

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    with manager.pinned_page(key) as view:
        frame_index = manager.page_table[key]

        assert view == expected
        assert view.readonly
        assert manager.pin_counts[frame_index] == 1

    # The page is automatically unpinned.
    assert manager.pin_counts[manager.page_table[key]] == 0

    # The memoryview is released after leaving the block.
    with pytest.raises(ValueError):
        view.tobytes()


def test_pinned_page_releases_on_exception(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)
    disk.write_page(0, bytes(PAGE_SIZE))

    manager = SharedPageManager(4)
    key = PageKey(file_path, 0)

    with (
        pytest.raises(RuntimeError, match="Test failure"),
        manager.pinned_page(key),
    ):
        frame_index = manager.page_table[key]

        assert manager.pin_counts[frame_index] == 1

        raise RuntimeError("Test failure")

    # Even after an exception, the frame is unpinned.
    assert manager.pin_counts[manager.page_table[key]] == 0


def test_invalid_page_read_preserves_cache(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    disk.write_page(0, bytes([42]) * PAGE_SIZE)

    manager = SharedPageManager(4)
    valid_key = PageKey(file_path, 0)
    invalid_key = PageKey(file_path, 99)

    manager.read_page(valid_key)

    # Reading a nonexistent page must fail.
    with pytest.raises(ValueError, match="Invalid page ID"):
        manager.read_page(invalid_key)

    # The existing cached page must remain available.
    assert valid_key in manager.page_table
    assert invalid_key not in manager.page_table

    # Failed reads must not increment the physical read counter.
    assert manager.stats()["reads"] == 1

    # No frames should remain pinned.
    assert all(count == 0 for count in manager.pin_counts)


def test_failed_read_does_not_evict_cached_page(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(4):
        disk.write_page(
            page_id,
            bytes([page_id]) * PAGE_SIZE,
        )

    manager = SharedPageManager(4)

    # Fill the cache.
    for page_id in range(4):
        manager.read_page(PageKey(file_path, page_id))

    original_table = manager.page_table.copy()
    original_victim = manager.next_victim

    # Page 99 does not exist.
    with pytest.raises(ValueError, match="Invalid page ID"):
        manager.read_page(PageKey(file_path, 99))

    # A failed read must not evict any existing page.
    assert manager.page_table == original_table
    assert manager.stats()["reads"] == 4
    assert all(count == 0 for count in manager.pin_counts)
    assert manager.next_victim == original_victim


def test_pages_from_different_files(tmp_path: Path):
    r_path = tmp_path / "R.db"
    s_path = tmp_path / "S.db"

    DiskManager(r_path).write_page(0, bytes([10]) * PAGE_SIZE)
    DiskManager(s_path).write_page(0, bytes([20]) * PAGE_SIZE)

    manager = SharedPageManager(4)

    r_key = PageKey(r_path, 0)
    s_key = PageKey(s_path, 0)

    assert manager.read_page(r_key) == bytes([10]) * PAGE_SIZE
    assert manager.read_page(s_key) == bytes([20]) * PAGE_SIZE

    # Both pages must occupy separate cache entries.
    assert len(manager.page_table) == 2
    assert manager.page_table[r_key] != manager.page_table[s_key]

    # Repeated accesses should hit the cache.
    manager.read_page(r_key)
    manager.read_page(s_key)

    assert manager.stats()["reads"] == 2
    assert manager.stats()["hits"] == 2


def test_eviction_across_different_files(tmp_path: Path):
    r_path = tmp_path / "R.db"
    s_path = tmp_path / "S.db"

    r_disk = DiskManager(r_path)
    s_disk = DiskManager(s_path)

    for page_id in range(4):
        r_disk.write_page(
            page_id,
            bytes([10 + page_id]) * PAGE_SIZE,
        )

    s_disk.write_page(0, bytes([99]) * PAGE_SIZE)

    manager = SharedPageManager(4)

    # Fill the cache with pages from R.
    for page_id in range(4):
        manager.read_page(PageKey(r_path, page_id))

    # Pin R's first page so it cannot be evicted.
    r_key = PageKey(r_path, 0)
    manager.pin_page(r_key)

    # Loading a page from S forces an eviction.
    s_key = PageKey(s_path, 0)
    result = manager.read_page(s_key)

    assert result == bytes([99]) * PAGE_SIZE

    # R's pinned page must remain cached.
    assert r_key in manager.page_table

    # R's second page should have been evicted.
    assert PageKey(r_path, 1) not in manager.page_table

    # S's page must now be cached.
    assert s_key in manager.page_table

    assert len(manager.page_table) == 4

    manager.unpin_page(r_key)


def test_disk_read_page_into(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    expected = bytes([42]) * PAGE_SIZE
    disk.write_page(0, expected)

    # Allocate the destination buffer.
    buffer = bytearray(PAGE_SIZE)

    # Keep a reference to verify that the buffer is reused.
    original_buffer = buffer

    disk.read_page_into(0, buffer)

    assert buffer is original_buffer
    assert buffer == expected


def test_read_page_into_invalid_page(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    disk.write_page(0, bytes([42]) * PAGE_SIZE)

    buffer = bytearray([99] * PAGE_SIZE)

    with pytest.raises(ValueError, match="Invalid page ID"):
        disk.read_page_into(99, buffer)

    # An invalid page must not modify the buffer.
    assert buffer == bytes([99]) * PAGE_SIZE


def test_read_page_into_invalid_buffer_size(tmp_path: Path):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    disk.write_page(0, bytes(PAGE_SIZE))

    buffer = bytearray(100)

    with pytest.raises(ValueError, match="Buffer must be exactly 4096 bytes"):
        disk.read_page_into(0, buffer)

    assert len(buffer) == 100


def test_read_page_into_rejects_truncated_file(tmp_path: Path):
    file_path = tmp_path / "R.db"

    # Create a file that is not a complete 4096-byte page.
    file_path.write_bytes(bytes([42]) * 100)

    disk = DiskManager(file_path)
    buffer = bytearray([99] * PAGE_SIZE)

    with pytest.raises(
        ValueError,
        match="Database file size is not a multiple of 4096",
    ):
        disk.read_page_into(0, buffer)

    # Validation fails before the buffer is modified.
    assert buffer == bytes([99]) * PAGE_SIZE


def test_read_page_into_short_read(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    disk.write_page(0, bytes([42]) * PAGE_SIZE)

    buffer = bytearray([99] * PAGE_SIZE)

    original_readinto = Path.open

    class ShortReadFile:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self.file.__exit__(exc_type, exc_value, traceback)

        def seek(self, *args):
            return self.file.seek(*args)

        def readinto(self, destination):
            destination[:100] = bytes([42]) * 100
            return 100

    def patched_open(path, *args, **kwargs):
        file = original_readinto(path, *args, **kwargs)

        if path == file_path and args and args[0] == "rb":
            return ShortReadFile(file)

        return file

    monkeypatch.setattr(Path, "open", patched_open)

    with pytest.raises(OSError, match="Failed to read page"):
        disk.read_page_into(0, buffer)

    # A partial read may modify the destination before failing.
    assert buffer[:100] == bytes([42]) * 100
    assert buffer[100:] == bytes([99]) * (PAGE_SIZE - 100)


def test_shared_manager_reads_into_empty_frame(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    expected = bytes([42]) * PAGE_SIZE
    disk.write_page(0, expected)

    manager = SharedPageManager(frames=4)
    key = PageKey(file_path, 0)

    def unexpected_read_page(self, page_id):
        raise AssertionError("read_page() should not be called")

    monkeypatch.setattr(DiskManager, "read_page", unexpected_read_page)

    result = manager.read_page(key)

    assert bytes(result) == expected
    assert manager.reads == 1
    assert len(manager.page_table) == 1


def test_occupied_frame_uses_direct_read(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(5):
        disk.write_page(page_id, bytes([page_id]) * PAGE_SIZE)

    manager = SharedPageManager(frames=4)

    # Fill all four cache frames.
    for page_id in range(4):
        manager.read_page(PageKey(file_path, page_id))

    original_read_into = DiskManager.read_page_into
    read_calls = []

    def tracked_read_into(self, page_id, buffer):
        read_calls.append(page_id)
        return original_read_into(self, page_id, buffer)

    def unexpected_read_page(self, page_id):
        raise AssertionError("read_page() should not be called")

    monkeypatch.setattr(DiskManager, "read_page_into", tracked_read_into)
    monkeypatch.setattr(DiskManager, "read_page", unexpected_read_page)

    # A fifth page requires eviction.
    result = manager.read_page(PageKey(file_path, 4))

    assert bytes(result) == bytes([4]) * PAGE_SIZE
    assert read_calls == [4]
    assert PageKey(file_path, 0) not in manager.page_table
    assert PageKey(file_path, 4) in manager.page_table
    assert len(manager.page_table) == 4
    assert manager.reads == 5


def test_failed_replacement_invalidates_victim(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "R.db"
    disk = DiskManager(file_path)

    for page_id in range(5):
        disk.write_page(page_id, bytes([page_id]) * PAGE_SIZE)

    manager = SharedPageManager(frames=4)

    for page_id in range(4):
        manager.read_page(PageKey(file_path, page_id))

    victim = PageKey(file_path, 0)
    replacement = PageKey(file_path, 4)

    def failing_read_into(self, page_id, buffer):
        buffer[:100] = bytes([99]) * 100
        raise OSError("Simulated partial read failure")

    monkeypatch.setattr(DiskManager, "read_page_into", failing_read_into)

    with pytest.raises(OSError, match="Simulated partial read failure"):
        manager.read_page(replacement)

    # The partially overwritten victim must no longer be cached.
    assert victim not in manager.page_table

    # The failed replacement must not be cached either.
    assert replacement not in manager.page_table

    # Other cached pages remain valid.
    for page_id in range(1, 4):
        key = PageKey(file_path, page_id)
        assert key in manager.page_table

    assert manager.reads == 4
