"""Tests for the Module 4 page-I/O cost model."""

import pytest

from src.optimizer.cost import (
    best_nested_loop_orientation,
    filter_cost,
    hash_join_cost,
    nested_loop_join_cost,
    projection_cost,
    scan_cost,
    sort_cost,
    sort_merge_join_cost,
    sort_passes,
)


def test_scan_cost():
    assert scan_cost(100) == 100


def test_empty_scan():
    assert scan_cost(0) == 0


def test_filter_cost():
    assert filter_cost() == 0


def test_projection_cost():
    assert projection_cost() == 0


def test_sort_fits_memory():
    assert sort_passes(20, 32) == 1
    assert sort_cost(20, 32) == 20


def test_sort_exactly_fills_memory():
    assert sort_passes(32, 32) == 1
    assert sort_cost(32, 32) == 32


def test_sort_requires_one_merge_pass():
    assert sort_passes(100, 32) == 2
    assert sort_cost(100, 32) == 300


def test_sort_requires_two_merge_passes():
    assert sort_passes(1000, 4) == 7
    assert sort_cost(1000, 4) == 13000


def test_sort_empty_relation():
    assert sort_passes(0, 32) == 0
    assert sort_cost(0, 32) == 0


def test_more_memory_reduces_sort_cost():
    assert sort_cost(1000, 32) < sort_cost(1000, 4)


def test_nested_loop_join():
    assert nested_loop_join_cost(100, 400, 32) == 1700


def test_nested_loop_exact_block():
    assert nested_loop_join_cost(60, 100, 32) == 260


def test_nested_loop_partial_block():
    assert nested_loop_join_cost(61, 100, 32) == 361


def test_nested_loop_more_frames():
    assert nested_loop_join_cost(100, 400, 64) == 900


def test_nested_loop_empty_input():
    assert nested_loop_join_cost(0, 100, 32) == 0
    assert nested_loop_join_cost(100, 0, 32) == 0


def test_sort_merge_join():
    assert sort_merge_join_cost(100, 400, 32) == 2000


def test_hash_join():
    assert hash_join_cost(100, 400, 32) == 1500


def test_hash_join_empty_input():
    assert hash_join_cost(0, 400, 32) == 0


def test_nested_loop_orientation():
    orientation, cost = best_nested_loop_orientation(
        400,
        10,
        32,
    )

    assert orientation == "right"
    assert cost == 410


def test_nested_loop_orientation_tie():
    orientation, cost = best_nested_loop_orientation(
        10,
        10,
        32,
    )

    assert orientation == "left"
    assert cost == 20


@pytest.mark.parametrize(
    "pages",
    [-1, -100],
)
def test_negative_page_counts_rejected(pages):
    with pytest.raises(ValueError):
        scan_cost(pages)

    with pytest.raises(ValueError):
        sort_cost(pages, 32)

    with pytest.raises(ValueError):
        nested_loop_join_cost(pages, 10, 32)

    with pytest.raises(ValueError):
        hash_join_cost(10, pages, 32)


@pytest.mark.parametrize(
    "pages",
    [1.5, "10", True],
)
def test_invalid_page_types_rejected(pages):
    with pytest.raises(TypeError):
        scan_cost(pages)


@pytest.mark.parametrize(
    "frames",
    [0, 1, 2],
)
def test_insufficient_sort_frames(frames):
    with pytest.raises(ValueError):
        sort_cost(100, frames)


@pytest.mark.parametrize(
    "frames",
    [0, 1, 2],
)
def test_insufficient_nested_loop_frames(frames):
    with pytest.raises(ValueError):
        nested_loop_join_cost(100, 200, frames)


def test_insufficient_hash_frames():
    with pytest.raises(ValueError):
        hash_join_cost(100, 200, 2)


def test_invalid_frame_type():
    with pytest.raises(TypeError):
        sort_cost(100, 3.5)


def test_join_cost_comparison():
    left_pages = 100
    right_pages = 400
    frames = 32

    nested = nested_loop_join_cost(
        left_pages,
        right_pages,
        frames,
    )
    merge = sort_merge_join_cost(
        left_pages,
        right_pages,
        frames,
    )
    hashed = hash_join_cost(
        left_pages,
        right_pages,
        frames,
    )

    assert hashed == 1500
    assert nested == 1700
    assert merge == 2000
    assert hashed < nested < merge
