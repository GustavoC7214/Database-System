
import pytest

from src.storage.disk_manager import PAGE_SIZE, DiskManager


@pytest.fixture
def disk(tmp_path):
    return DiskManager(tmp_path / "test.db")


def test_creates_database_file(tmp_path):
    path = tmp_path / "test.db"

    DiskManager(path)

    assert path.exists()
    assert path.stat().st_size == 0


def test_new_database_has_zero_pages(disk):
    assert disk.page_count() == 0


def test_allocate_page(disk):
    page_id = disk.allocate_page()

    assert page_id == 0
    assert disk.page_count() == 1
    assert disk.read_page(0) == bytes(PAGE_SIZE)


def test_allocate_multiple_pages(disk):
    assert disk.allocate_page() == 0
    assert disk.allocate_page() == 1
    assert disk.allocate_page() == 2

    assert disk.page_count() == 3
    assert disk.file_path.stat().st_size == 3 * PAGE_SIZE


def test_write_and_read_page(disk):
    disk.allocate_page()

    data = b"A" * PAGE_SIZE
    disk.write_page(0, data)

    assert disk.read_page(0) == data


def test_pages_are_independent(disk):
    disk.allocate_page()
    disk.allocate_page()

    disk.write_page(0, b"A" * PAGE_SIZE)
    disk.write_page(1, b"B" * PAGE_SIZE)

    assert disk.read_page(0) == b"A" * PAGE_SIZE
    assert disk.read_page(1) == b"B" * PAGE_SIZE


def test_data_persists_after_reopening(tmp_path):
    path = tmp_path / "test.db"

    disk = DiskManager(path)
    disk.allocate_page()
    disk.write_page(0, b"X" * PAGE_SIZE)

    reopened = DiskManager(path)

    assert reopened.page_count() == 1
    assert reopened.read_page(0) == b"X" * PAGE_SIZE


@pytest.mark.parametrize("page_id", [-1, 0, 10])
def test_read_invalid_page(disk, page_id):
    with pytest.raises(ValueError):
        disk.read_page(page_id)


def test_write_invalid_page(disk):
    with pytest.raises(ValueError):
        disk.write_page(2, bytes(PAGE_SIZE))


def test_write_wrong_page_size(disk):
    disk.allocate_page()

    with pytest.raises(ValueError):
        disk.write_page(0, b"too short")


def test_reject_corrupted_file_size(tmp_path):
    path = tmp_path / "corrupted.db"
    path.write_bytes(b"invalid")

    disk = DiskManager(path)

    with pytest.raises(ValueError):
        disk.page_count()
