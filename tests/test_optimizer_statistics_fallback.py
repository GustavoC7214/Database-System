"""Tests for deterministic optimizer fallback statistics."""

from src.optimizer.statistics import TableStatistics
from src.optimizer.statistics_fallback import (
    DEFAULT_PAGES,
    DEFAULT_ROWS,
    DEFAULT_WIDTH,
    complete_statistics,
    fallback_table_statistics,
)


def test_fallback_values():
    stats = fallback_table_statistics("Emp")

    assert stats.table == "Emp"
    assert stats.n_tuples == DEFAULT_ROWS
    assert stats.n_pages == DEFAULT_PAGES
    assert stats.width == DEFAULT_WIDTH
    assert stats.columns == {}


def test_fallback_is_deterministic():
    assert fallback_table_statistics("Emp") == fallback_table_statistics("Emp")


def test_existing_statistics_are_preserved():
    actual = TableStatistics(
        table="Emp",
        n_tuples=250,
        n_pages=8,
        width=16.0,
    )

    result = complete_statistics(
        {"Emp", "Dept"},
        {"Emp": actual},
    )

    assert result["Emp"] is actual
    assert result["Dept"] == fallback_table_statistics("Dept")


def test_input_dictionary_is_not_modified():
    original = {}

    result = complete_statistics({"Emp"}, original)

    assert original == {}
    assert "Emp" in result


def test_empty_table_set():
    assert complete_statistics(set(), {}) == {}
