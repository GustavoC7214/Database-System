
import pytest

from src.storage.slotted_page import SlottedPage


def test_empty_page():
    page = SlottedPage(3)

    assert page.page_id == 3
    assert page.slot_count == 0
    assert page.free_end == 4096
    assert page.free_space == 4088


def test_professor_layout_example():
    page = SlottedPage(3)

    assert page.insert(b"A" * 13) == 0
    assert page.slot_count == 1
    assert page.free_end == 4083
    assert page.free_space == 4071
    assert page.get_slot(0) == (4083, 13)

    assert page.insert(b"B" * 20) == 1
    assert page.slot_count == 2
    assert page.free_end == 4063
    assert page.free_space == 4047
    assert page.get_slot(1) == (4063, 20)

    assert page.insert(b"C" * 13) == 2
    assert page.slot_count == 3
    assert page.free_end == 4050
    assert page.free_space == 4030
    assert page.get_slot(2) == (4050, 13)

    page.delete(1)

    assert page.slot_count == 3
    assert page.free_end == 4050
    assert page.free_space == 4030
    assert page.get_slot(1) == (0, 0)


def test_get_records():
    page = SlottedPage(0)

    page.insert(b"hello")
    page.insert(b"world")

    assert page.get(0) == b"hello"
    assert page.get(1) == b"world"


def test_deleted_record_raises_error():
    page = SlottedPage(0)
    page.insert(b"hello")
    page.delete(0)

    with pytest.raises(ValueError, match="deleted"):
        page.get(0)


def test_double_delete_raises_error():
    page = SlottedPage(0)
    page.insert(b"hello")
    page.delete(0)

    with pytest.raises(ValueError, match="already deleted"):
        page.delete(0)


def test_invalid_slot_raises_error():
    page = SlottedPage(0)

    with pytest.raises(ValueError):
        page.get(-1)

    with pytest.raises(ValueError):
        page.get(0)


def test_slots_are_not_reused():
    page = SlottedPage(0)

    page.insert(b"first")
    page.insert(b"second")
    page.delete(0)

    assert page.insert(b"third") == 2
    assert page.get_slot(0) == (0, 0)
    assert page.get(2) == b"third"


def test_page_serialization_round_trip():
    page = SlottedPage(5)
    page.insert(b"hello")
    page.insert(b"world")

    restored = SlottedPage(5, page.to_bytes())

    assert restored.page_id == 5
    assert restored.slot_count == 2
    assert restored.get(0) == b"hello"
    assert restored.get(1) == b"world"


def test_wrong_page_id_rejected():
    page = SlottedPage(5)

    with pytest.raises(ValueError):
        SlottedPage(6, page.to_bytes())


def test_record_too_large():
    page = SlottedPage(0)

    with pytest.raises(ValueError, match="Record is too large"):
        page.insert(b"A" * 4085)

    assert page.slot_count == 0
    assert page.free_space == 4088


def test_fixed_record_capacity():
    page = SlottedPage(0)

    for slot_no in range(240):
        assert page.insert(b"A" * 13) == slot_no

    assert page.slot_count == 240
    assert page.insert(b"A" * 13) is None


def test_insert_rejects_oversized_record():
    page = SlottedPage(1)

    with pytest.raises(ValueError, match="Record is too large"):
        page.insert(b"x" * 4085)

    assert page.slot_count == 0
    assert page.free_space == 4088
