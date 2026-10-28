from pathlib import Path

import pytest

from src.execution.page import PageKey


def test_page_key_fields():
    key = PageKey(Path("R.db"), 1)

    assert key.file_path == Path("R.db")
    assert key.page_id == 1


def test_different_files_have_different_keys():
    first = PageKey(Path("R.db"), 1)
    second = PageKey(Path("S.db"), 1)

    assert first != second


def test_same_page_has_equal_keys():
    first = PageKey(Path("R.db"), 2)
    second = PageKey(Path("R.db"), 2)

    assert first == second
    assert hash(first) == hash(second)


def test_page_key_can_be_dictionary_key():
    key = PageKey(Path("R.db"), 3)
    pages = {key: "cached"}

    assert pages[PageKey(Path("R.db"), 3)] == "cached"


def test_negative_page_id_rejected():
    with pytest.raises(ValueError, match="Page ID cannot be negative"):
        PageKey(Path("R.db"), -1)


def test_page_key_is_immutable():
    key = PageKey(Path("R.db"), 1)

    with pytest.raises(AttributeError):
        key.page_id = 2  # type: ignore[misc]
