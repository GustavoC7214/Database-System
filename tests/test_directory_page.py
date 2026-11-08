import struct

import pytest

from src.storage.directory_page import (
    MAX_ENTRIES,
    NO_NEXT_PAGE,
    DirectoryPage,
)
from src.storage.disk_manager import PAGE_SIZE


def test_empty_directory_page():
    page = DirectoryPage(0)

    assert page.page_id == 0
    assert page.next_dir_page == NO_NEXT_PAGE
    assert page.entry_count == 0
    assert len(page.to_bytes()) == PAGE_SIZE


def test_exact_header_layout():
    page = DirectoryPage(3)
    data = page.to_bytes()

    assert struct.unpack_from("<I", data, 0)[0] == 3
    assert struct.unpack_from("<I", data, 4)[0] == 0xFFFFFFFF
    assert struct.unpack_from("<H", data, 8)[0] == 0


def test_add_directory_entry():
    page = DirectoryPage(0)

    index = page.add_entry(1, 4088)

    assert index == 0
    assert page.entry_count == 1
    assert page.get_entry(0) == (1, 4088)


def test_exact_entry_layout():
    page = DirectoryPage(0)
    page.add_entry(1, 4088)
    page.add_entry(2, 4071)

    data = page.to_bytes()

    assert struct.unpack_from("<IH", data, 10) == (1, 4088)
    assert struct.unpack_from("<IH", data, 16) == (2, 4071)
    assert struct.unpack_from("<H", data, 8)[0] == 2


def test_update_entry():
    page = DirectoryPage(0)
    page.add_entry(1, 4088)

    page.update_entry(0, 4071)

    assert page.get_entry(0) == (1, 4071)
    assert page.entry_count == 1


def test_next_directory_page():
    page = DirectoryPage(0)

    page.next_dir_page = 5

    assert page.next_dir_page == 5
    assert struct.unpack_from("<I", page.to_bytes(), 4)[0] == 5


def test_directory_page_serialization():
    page = DirectoryPage(0)
    page.add_entry(1, 4088)
    page.add_entry(2, 4071)
    page.next_dir_page = 10

    restored = DirectoryPage(0, page.to_bytes())

    assert restored.page_id == 0
    assert restored.next_dir_page == 10
    assert restored.entry_count == 2
    assert restored.get_entry(0) == (1, 4088)
    assert restored.get_entry(1) == (2, 4071)


def test_directory_capacity():
    page = DirectoryPage(0)

    assert MAX_ENTRIES == 681

    for index in range(MAX_ENTRIES):
        assert page.add_entry(index + 1, 4088) == index

    assert page.entry_count == 681

    with pytest.raises(ValueError, match="full"):
        page.add_entry(682, 4088)


def test_invalid_entry_index():
    page = DirectoryPage(0)

    with pytest.raises(ValueError):
        page.get_entry(0)

    with pytest.raises(ValueError):
        page.update_entry(-1, 100)


def test_invalid_free_space():
    page = DirectoryPage(0)

    with pytest.raises(ValueError):
        page.add_entry(1, -1)

    with pytest.raises(ValueError):
        page.add_entry(1, 4097)


def test_invalid_data_page_id():
    page = DirectoryPage(0)

    with pytest.raises(ValueError):
        page.add_entry(-1, 4088)

    with pytest.raises(ValueError):
        page.add_entry(NO_NEXT_PAGE, 4088)


def test_wrong_page_id():
    page = DirectoryPage(0)

    with pytest.raises(ValueError):
        DirectoryPage(1, page.to_bytes())


def test_wrong_page_size():
    with pytest.raises(ValueError):
        DirectoryPage(0, b"invalid")


def test_rejects_impossible_free_space():
    directory = DirectoryPage(0)

    with pytest.raises(ValueError, match="Invalid free-space value"):
        directory.add_entry(1, 4089)

    assert directory.entry_count == 0
