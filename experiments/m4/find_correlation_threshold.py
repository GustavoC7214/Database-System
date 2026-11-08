"""Explore join-algorithm thresholds for correlated selection estimates.

This experiment does not modify production optimizer code or database data.
It uses the existing analytical cost formulas to identify configurations
where correcting a cardinality estimate changes the preferred algorithm.
"""

import argparse
import csv
from pathlib import Path

from src.optimizer.cardinality import estimate_pages
from src.optimizer.cost import (
    hash_join_cost,
    nested_loop_join_cost,
    sort_merge_join_cost,
)

DEFAULT_OUTPUT = Path("experiments/m4/results/correlation_thresholds.csv")

ESTIMATED_CUSTOMERS = 180
ACTUAL_CUSTOMERS = 600

# Four integer columns per Customers record.
CUSTOMER_WIDTH = 16.0


def select_algorithm(
    left_pages: int,
    right_pages: int,
    frames: int,
) -> tuple[str, int]:
    """Return the cheapest algorithm and its analytical I/O cost."""
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

    cost, _, algorithm = min(candidates)
    return algorithm, cost


def find_thresholds() -> list[dict[str, int | str]]:
    """Find page-count configurations where correction changes the plan."""
    estimated_pages = estimate_pages(
        ESTIMATED_CUSTOMERS,
        CUSTOMER_WIDTH,
    )
    actual_pages = estimate_pages(
        ACTUAL_CUSTOMERS,
        CUSTOMER_WIDTH,
    )

    results = []

    for frames in (4, 8, 16, 32):
        for right_pages in range(1, 2001):
            original_algorithm, original_cost = select_algorithm(
                estimated_pages,
                right_pages,
                frames,
            )
            corrected_algorithm, corrected_cost = select_algorithm(
                actual_pages,
                right_pages,
                frames,
            )

            if original_algorithm == corrected_algorithm:
                continue

            results.append(
                {
                    "frames": frames,
                    "right_pages": right_pages,
                    "estimated_left_pages": estimated_pages,
                    "corrected_left_pages": actual_pages,
                    "original_algorithm": original_algorithm,
                    "corrected_algorithm": corrected_algorithm,
                    "original_cost": original_cost,
                    "corrected_cost": corrected_cost,
                }
            )

    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    results = find_thresholds()

    print(f"Configurations with different algorithms: {len(results)}")

    for result in results[:20]:
        print(result)

    if not results:
        print("No algorithm-selection thresholds found.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0]),
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
