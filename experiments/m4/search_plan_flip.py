"""Find cardinality errors that change the optimizer's join algorithm."""

from dataclasses import dataclass

from src.optimizer.cardinality import estimate_pages
from src.optimizer.cost import (
    hash_join_cost,
    nested_loop_join_cost,
    sort_merge_join_cost,
)

WIDTH = 16.0
FRAMES = (4, 8, 16, 32)
ROW_COUNTS = (
    10,
    25,
    50,
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
)
RIGHT_PAGES = (5, 10, 25, 50, 100, 250, 500, 1_000)


@dataclass(frozen=True)
class PlanFlip:
    frames: int
    estimated_rows: int
    actual_rows: int
    right_pages: int
    estimated_pages: int
    actual_pages: int
    original_algorithm: str
    corrected_algorithm: str


def choose_algorithm(
    left_pages: int,
    right_pages: int,
    frames: int,
) -> str:
    candidates = [
        (
            nested_loop_join_cost(left_pages, right_pages, frames),
            0,
            "nested_loop_join",
        ),
        (
            hash_join_cost(left_pages, right_pages, frames),
            1,
            "hash_join",
        ),
        (
            sort_merge_join_cost(left_pages, right_pages, frames),
            2,
            "sort_merge_join",
        ),
    ]
    return min(candidates)[2]


def search_plan_flips() -> list[PlanFlip]:
    results = []

    for frames in FRAMES:
        for estimated_rows in ROW_COUNTS:
            for actual_rows in ROW_COUNTS:
                if actual_rows <= estimated_rows:
                    continue

                estimated_pages = estimate_pages(estimated_rows, WIDTH)
                actual_pages = estimate_pages(actual_rows, WIDTH)

                for right_pages in RIGHT_PAGES:
                    original = choose_algorithm(
                        estimated_pages,
                        right_pages,
                        frames,
                    )
                    corrected = choose_algorithm(
                        actual_pages,
                        right_pages,
                        frames,
                    )

                    if original != corrected:
                        results.append(
                            PlanFlip(
                                frames=frames,
                                estimated_rows=estimated_rows,
                                actual_rows=actual_rows,
                                right_pages=right_pages,
                                estimated_pages=estimated_pages,
                                actual_pages=actual_pages,
                                original_algorithm=original,
                                corrected_algorithm=corrected,
                            )
                        )

    return results


def main() -> None:
    results = search_plan_flips()

    print(f"Plan-changing configurations: {len(results)}")

    for result in results[:25]:
        print(result)


if __name__ == "__main__":
    main()
