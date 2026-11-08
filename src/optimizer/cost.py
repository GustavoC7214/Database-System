"""Page-I/O cost formulas for physical query operators.

Costs are estimates in page reads and writes, not elapsed time.
Each function estimates one operator independently.
"""

from math import ceil

MIN_SORT_FRAMES = 3
MIN_NESTED_LOOP_FRAMES = 3
MIN_HASH_FRAMES = 3


def _check_pages(pages: int) -> None:
    if isinstance(pages, bool) or not isinstance(pages, int):
        raise TypeError("Page count must be an integer")
    if pages < 0:
        raise ValueError("Page count cannot be negative")


def _check_frames(frames: int, minimum: int) -> None:
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("Buffer frames must be an integer")
    if frames < minimum:
        raise ValueError(f"Operation requires at least {minimum} buffer frames")


def scan_cost(pages: int) -> int:
    """Cost of reading a relation sequentially."""
    _check_pages(pages)
    return pages


def filter_cost() -> int:
    """Additional I/O of a streaming filter."""
    return 0


def projection_cost() -> int:
    """Additional I/O of a streaming projection."""
    return 0


def sort_passes(pages: int, frames: int) -> int:
    """Number of external-sort passes, including run generation.

    Initial runs contain up to B pages. Subsequent passes
    merge up to B-1 runs at a time.
    """
    _check_pages(pages)
    _check_frames(frames, MIN_SORT_FRAMES)

    if pages == 0:
        return 0

    runs = ceil(pages / frames)
    passes = 1

    while runs > 1:
        runs = ceil(runs / (frames - 1))
        passes += 1

    return passes


def sort_cost(pages: int, frames: int) -> int:
    """External merge sort with pipelined final output.

    Each nonfinal pass reads and writes M pages (2M).
    The final pass reads M pages without materializing
    another output relation.
    """
    passes = sort_passes(pages, frames)

    if passes == 0:
        return 0

    return 2 * pages * (passes - 1) + pages


def nested_loop_join_cost(
    outer_pages: int,
    inner_pages: int,
    frames: int,
) -> int:
    """Block nested-loop join with B-2 outer buffer pages."""
    _check_pages(outer_pages)
    _check_pages(inner_pages)
    _check_frames(frames, MIN_NESTED_LOOP_FRAMES)

    if outer_pages == 0 or inner_pages == 0:
        return 0

    outer_blocks = ceil(outer_pages / (frames - 2))

    return outer_pages + outer_blocks * inner_pages


def sort_merge_join_cost(
    left_pages: int,
    right_pages: int,
    frames: int,
) -> int:
    """Sort both inputs and perform a merge scan.

    Uses the assignment's additive formula:
    Sort(M) + Sort(N) + M + N.

    Assumes the merge scan can process matching-key groups
    without extra spill I/O.
    """
    _check_pages(left_pages)
    _check_pages(right_pages)
    _check_frames(frames, MIN_SORT_FRAMES)

    if left_pages == 0 or right_pages == 0:
        return 0

    return (
        sort_cost(left_pages, frames)
        + sort_cost(right_pages, frames)
        + left_pages
        + right_pages
    )


def hash_join_cost(
    left_pages: int,
    right_pages: int,
    frames: int,
) -> int:
    """One-level Grace hash join: 3(M+N) page I/Os.

    Assumes partitions fit during the build/probe phase.
    Recursive repartitioning is not modeled here.
    """
    _check_pages(left_pages)
    _check_pages(right_pages)
    _check_frames(frames, MIN_HASH_FRAMES)

    if left_pages == 0 or right_pages == 0:
        return 0

    return 3 * (left_pages + right_pages)


def best_nested_loop_orientation(
    left_pages: int,
    right_pages: int,
    frames: int,
) -> tuple[str, int]:
    """Choose the cheaper outer input for block nested-loop join.

    Returns ('left' or 'right', estimated I/O).
    Ties prefer the original left input.
    """
    left_outer = nested_loop_join_cost(
        left_pages,
        right_pages,
        frames,
    )
    right_outer = nested_loop_join_cost(
        right_pages,
        left_pages,
        frames,
    )

    if right_outer < left_outer:
        return "right", right_outer

    return "left", left_outer
