
import pytest

from src.storage.buffer_pool import BufferPool
from src.storage.disk_manager import PAGE_SIZE, DiskManager


@pytest.fixture
def disk(tmp_path):
    manager = DiskManager(tmp_path / "test.db")

    for _ in range(10):
        manager.allocate_page()

    return manager


def test_buffer_pool_initialization(disk):
    pool = BufferPool(disk, frames=3)

    assert pool.capacity == 3
    assert pool.policy == "lru"
    assert len(pool.frames) == 3
    assert pool.page_table == {}
    assert pool.stats() == {
        "hits": 0,
        "misses": 0,
        "evictions": 0,
        "reads": 0,
        "writes": 0,
    }


def test_fetch_page_miss(disk):
    pool = BufferPool(disk, frames=3)

    data = pool.fetch_page(1)

    assert len(data) == PAGE_SIZE
    assert pool.frames[pool.page_table[1]].pin_count == 1
    assert pool.stats()["misses"] == 1
    assert pool.stats()["reads"] == 1


def test_fetch_page_hit(disk):
    pool = BufferPool(disk, frames=3)

    pool.fetch_page(1)
    pool.fetch_page(1)

    assert pool.stats()["hits"] == 1
    assert pool.stats()["misses"] == 1
    assert pool.frames[pool.page_table[1]].pin_count == 2


def test_unpin_page(disk):
    pool = BufferPool(disk, frames=3)

    pool.fetch_page(1)
    pool.fetch_page(1)

    pool.unpin_page(1)
    assert pool.frames[pool.page_table[1]].pin_count == 1

    pool.unpin_page(1)
    assert pool.frames[pool.page_table[1]].pin_count == 0


def test_unpin_unpinned_page_rejected(disk):
    pool = BufferPool(disk, frames=3)

    pool.fetch_page(1)
    pool.unpin_page(1)

    with pytest.raises(ValueError, match="already unpinned"):
        pool.unpin_page(1)


def test_unpin_nonresident_page_rejected(disk):
    pool = BufferPool(disk, frames=3)

    with pytest.raises(ValueError, match="not in the buffer pool"):
        pool.unpin_page(1)


def test_pinned_page_cannot_be_evicted(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)

    pool.fetch_page(2)
    pool.unpin_page(2)

    pool.fetch_page(3)

    assert 1 in pool.page_table
    assert 2 not in pool.page_table
    assert 3 in pool.page_table


def test_all_frames_pinned(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)
    pool.fetch_page(2)

    with pytest.raises(RuntimeError, match="pinned"):
        pool.fetch_page(3)


def test_lru_worked_example(disk):
    pool = BufferPool(disk, frames=3, policy="lru")

    for page_id in [1, 2, 3, 1, 4, 2]:
        pool.fetch_page(page_id)
        pool.unpin_page(page_id)

    assert pool.stats() == {
        "hits": 1,
        "misses": 5,
        "evictions": 2,
        "reads": 5,
        "writes": 0,
    }


def test_dirty_page_written_on_eviction(disk):
    pool = BufferPool(disk, frames=1)

    data = pool.fetch_page(1)
    data[0:5] = b"hello"
    pool.unpin_page(1, dirty=True)

    pool.fetch_page(2)
    pool.unpin_page(2)

    assert disk.read_page(1)[:5] == b"hello"
    assert pool.stats()["writes"] == 1


def test_clean_page_not_written_on_eviction(disk):
    pool = BufferPool(disk, frames=1)

    pool.fetch_page(1)
    pool.unpin_page(1)

    pool.fetch_page(2)
    pool.unpin_page(2)

    assert pool.stats()["writes"] == 0
    assert pool.stats()["evictions"] == 1


def test_dirty_flag_remains_true(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)
    pool.unpin_page(1, dirty=True)

    pool.fetch_page(1)
    pool.unpin_page(1, dirty=False)

    frame = pool.frames[pool.page_table[1]]
    assert frame.dirty is True


def test_invalid_policy_rejected(disk):
    with pytest.raises(ValueError, match="Unknown replacement policy"):
        BufferPool(disk, frames=3, policy="random")


def test_zero_frames_rejected(disk):
    with pytest.raises(ValueError, match="at least one frame"):
        BufferPool(disk, frames=0)


def test_clock_worked_example(disk):
    pool = BufferPool(disk, frames=3, policy="clock")

    for page_id in [1, 2, 3, 1, 4, 2]:
        pool.fetch_page(page_id)
        pool.unpin_page(page_id)

    assert pool.stats() == {
        "hits": 2,
        "misses": 4,
        "evictions": 1,
        "reads": 4,
        "writes": 0,
    }


def test_clock_hand_advances(disk):
    pool = BufferPool(disk, frames=3, policy="clock")

    pool.fetch_page(1)
    pool.unpin_page(1)
    assert pool.clock_hand == 1

    pool.fetch_page(2)
    pool.unpin_page(2)
    assert pool.clock_hand == 2

    pool.fetch_page(3)
    pool.unpin_page(3)
    assert pool.clock_hand == 0


def test_clock_does_not_evict_pinned_page(disk):
    pool = BufferPool(disk, frames=2, policy="clock")

    pool.fetch_page(1)

    pool.fetch_page(2)
    pool.unpin_page(2)

    pool.fetch_page(3)
    pool.unpin_page(3)

    assert 1 in pool.page_table
    assert 2 not in pool.page_table
    assert 3 in pool.page_table


def test_clock_all_frames_pinned(disk):
    pool = BufferPool(disk, frames=2, policy="clock")

    pool.fetch_page(1)
    pool.fetch_page(2)

    with pytest.raises(RuntimeError, match="pinned"):
        pool.fetch_page(3)


def test_clock_dirty_page_written_on_eviction(disk):
    pool = BufferPool(disk, frames=1, policy="clock")

    data = pool.fetch_page(1)
    data[:5] = b"hello"
    pool.unpin_page(1, dirty=True)

    pool.fetch_page(2)
    pool.unpin_page(2)

    assert disk.read_page(1)[:5] == b"hello"
    assert pool.stats()["writes"] == 1


def test_flush_all_writes_dirty_pages(disk):
    pool = BufferPool(disk, frames=3)

    first = pool.fetch_page(1)
    first[:5] = b"hello"
    pool.unpin_page(1, dirty=True)

    second = pool.fetch_page(2)
    second[:5] = b"world"
    pool.unpin_page(2, dirty=True)

    pool.flush_all()

    assert disk.read_page(1)[:5] == b"hello"
    assert disk.read_page(2)[:5] == b"world"
    assert pool.stats()["writes"] == 2


def test_flush_all_skips_clean_pages(disk):
    pool = BufferPool(disk, frames=3)

    pool.fetch_page(1)
    pool.unpin_page(1)

    pool.fetch_page(2)
    pool.unpin_page(2)

    pool.flush_all()

    assert pool.stats()["writes"] == 0


def test_flush_all_clears_dirty_flags(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)
    pool.unpin_page(1, dirty=True)

    frame = pool.frames[pool.page_table[1]]
    assert frame.dirty is True

    pool.flush_all()

    assert frame.dirty is False


def test_flush_all_does_not_write_twice(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)
    pool.unpin_page(1, dirty=True)

    pool.flush_all()
    assert pool.stats()["writes"] == 1

    pool.flush_all()
    assert pool.stats()["writes"] == 1


def test_flush_all_preserves_cached_pages(disk):
    pool = BufferPool(disk, frames=2)

    pool.fetch_page(1)
    pool.unpin_page(1, dirty=True)

    pool.flush_all()

    assert 1 in pool.page_table

    pool.fetch_page(1)
    pool.unpin_page(1)

    assert pool.stats()["hits"] == 1
    assert pool.stats()["misses"] == 1
    assert pool.stats()["evictions"] == 0


def test_new_page_allocation(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=2)

    page_id, data = pool.new_page()

    assert page_id == 0
    assert disk.page_count() == 1
    assert len(data) == PAGE_SIZE
    assert data == bytes(PAGE_SIZE)


def test_new_page_is_pinned_and_dirty(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=2)

    page_id, _ = pool.new_page()
    frame = pool.frames[pool.page_table[page_id]]

    assert frame.pin_count == 1
    assert frame.dirty is True
    assert frame.reference_bit is True


def test_new_page_can_be_modified_and_flushed(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=2)

    page_id, data = pool.new_page()
    data[:5] = b"hello"

    pool.unpin_page(page_id, dirty=True)
    pool.flush_all()

    assert disk.read_page(page_id)[:5] == b"hello"
    assert pool.stats()["writes"] == 1


def test_new_page_does_not_count_as_disk_read(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=2)

    pool.new_page()

    assert pool.stats()["reads"] == 0
    assert pool.stats()["misses"] == 0
    assert pool.stats()["hits"] == 0


def test_new_page_evicts_unpinned_page(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=1)

    first_id, first_data = pool.new_page()
    first_data[:5] = b"first"
    pool.unpin_page(first_id, dirty=True)

    second_id, second_data = pool.new_page()

    assert second_id == 1
    assert second_data == bytes(PAGE_SIZE)
    assert first_id not in pool.page_table
    assert second_id in pool.page_table
    assert pool.stats()["evictions"] == 1
    assert pool.stats()["writes"] == 1
    assert disk.read_page(first_id)[:5] == b"first"


def test_new_page_rejected_when_all_frames_pinned(tmp_path):
    disk = DiskManager(tmp_path / "new.db")
    pool = BufferPool(disk, frames=1)

    pool.new_page()

    with pytest.raises(RuntimeError, match="pinned"):
        pool.new_page()

    # A failed allocation must not create an extra disk page.
    assert disk.page_count() == 1


def test_failed_fetch_preserves_clock_state(tmp_path):
    disk = DiskManager(tmp_path / "test.db")

    for _ in range(3):
        disk.allocate_page()

    pool = BufferPool(disk, frames=2, policy="clock")

    for page_id in (0, 1):
        pool.fetch_page(page_id)
        pool.unpin_page(page_id)

    before_hand = pool.clock_hand
    before_bits = [frame.reference_bit for frame in pool.frames]
    before_table = pool.page_table.copy()
    before_stats = pool.stats().copy()

    with pytest.raises((ValueError, IndexError)):
        pool.fetch_page(999)

    assert pool.clock_hand == before_hand
    assert [frame.reference_bit for frame in pool.frames] == before_bits
    assert pool.page_table == before_table
    assert pool.stats() == before_stats


def test_dirty_eviction_persists_data(tmp_path):
    disk = DiskManager(tmp_path / "test.db")
    disk.allocate_page()
    disk.allocate_page()

    pool = BufferPool(disk, frames=1, policy="lru")

    data = pool.fetch_page(0)
    data[0:5] = b"hello"
    pool.unpin_page(0, dirty=True)

    pool.fetch_page(1)
    pool.unpin_page(1)

    assert disk.read_page(0)[:5] == b"hello"

    stats = pool.stats()
    assert stats["misses"] == 2
    assert stats["evictions"] == 1
    assert stats["reads"] == 2
    assert stats["writes"] == 1


def test_clock_dirty_eviction_persists_data(tmp_path):
    disk = DiskManager(tmp_path / "test.db")

    for _ in range(3):
        disk.allocate_page()

    pool = BufferPool(disk, frames=2, policy="clock")

    first = pool.fetch_page(0)
    first[:5] = b"hello"
    pool.unpin_page(0, dirty=True)

    pool.fetch_page(1)
    pool.unpin_page(1)

    # Both frames are occupied; fetching page 2 requires eviction.
    pool.fetch_page(2)
    pool.unpin_page(2)

    assert disk.read_page(0)[:5] == b"hello"

    stats = pool.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 3
    assert stats["evictions"] == 1
    assert stats["reads"] == 3
    assert stats["writes"] == 1
