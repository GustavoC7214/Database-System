"""Experiment 3: Join crossover analysis.

Run:
    python3 -m experiments.m2.join_crossover

Output:
    experiments/m2/results/join_crossover.csv
"""

import csv
import shutil
from pathlib import Path

from experiments.m2.join_costs import (
    ALGORITHMS,
    RESULTS_DIR,
    create_database,
    measure,
)

DATABASE_DIR = RESULTS_DIR / "join_crossover_db"
OUTPUT_FILE = RESULTS_DIR / "join_crossover.csv"

# Sweep A: fixed relation sizes, varying available memory.
MEMORY_FRAMES = (4, 6, 8, 12, 16, 24, 32, 64, 128, 256)
FIXED_LEFT_ROWS = 2000
FIXED_RIGHT_ROWS = 1000

# Sweep B: fixed memory, varying relation sizes.
FIXED_FRAMES = 16
RELATION_ROW_COUNTS = (100, 250, 500, 1000, 2000, 4000)

FIELDNAMES = (
    "sweep",
    "size",
    "algorithm",
    "frames",
    "left_rows",
    "right_rows",
    "output_rows",
    "input_page_reads",
    "temp_page_reads",
    "temp_page_writes",
    "total_page_reads",
    "total_page_writes",
    "total_page_io",
    "comparisons",
    "elapsed_seconds",
)


def run_configuration(
    database: Path,
    label: str,
    frames: int,
    left_rows: int,
    right_rows: int,
    sweep: str,
) -> list[dict]:
    """Execute all join algorithms against one dataset and frame budget."""
    results = []

    for algorithm in ALGORITHMS:
        print(
            f"Running {sweep:6} "
            f"left={left_rows:5} "
            f"right={right_rows:5} "
            f"B={frames:3} "
            f"{algorithm:18}",
            flush=True,
        )

        measurement = measure(
            database=database,
            algorithm=algorithm,
            frames=frames,
            size=label,
            left_count=left_rows,
            right_count=right_rows,
        )

        measurement["sweep"] = sweep
        results.append(measurement)

        print(
            f"  I/O={measurement['total_page_io']:7} "
            f"time={measurement['elapsed_seconds']:.4f}s",
            flush=True,
        )

    return results


def memory_sweep() -> list[dict]:
    """Hold relation sizes fixed while varying B."""
    database = DATABASE_DIR / "memory"

    create_database(
        database,
        FIXED_LEFT_ROWS,
        FIXED_RIGHT_ROWS,
    )

    results = []

    for frames in MEMORY_FRAMES:
        results.extend(
            run_configuration(
                database=database,
                label="fixed_large",
                frames=frames,
                left_rows=FIXED_LEFT_ROWS,
                right_rows=FIXED_RIGHT_ROWS,
                sweep="memory",
            )
        )

    return results


def relation_sweep() -> list[dict]:
    """Hold B fixed while increasing relation sizes."""
    results = []

    for left_rows in RELATION_ROW_COUNTS:
        right_rows = left_rows // 2
        label = f"rows_{left_rows}"
        database = DATABASE_DIR / label

        create_database(database, left_rows, right_rows)

        results.extend(
            run_configuration(
                database=database,
                label=label,
                frames=FIXED_FRAMES,
                left_rows=left_rows,
                right_rows=right_rows,
                sweep="relation",
            )
        )

    return results


def print_summary(results: list[dict]) -> None:
    """Print the minimum-I/O and fastest algorithm per configuration."""
    print("\nCROSSOVER SUMMARY")
    print("-" * 80)

    configurations = {}

    for result in results:
        key = (
            result["sweep"],
            result["frames"],
            result["left_rows"],
            result["right_rows"],
        )
        configurations.setdefault(key, []).append(result)

    for key, group in configurations.items():
        lowest_io = min(group, key=lambda row: row["total_page_io"])
        fastest = min(group, key=lambda row: row["elapsed_seconds"])

        sweep, frames, left_rows, right_rows = key

        print(
            f"{sweep:8} "
            f"B={frames:3} "
            f"rows={left_rows:5}/{right_rows:5} "
            f"lowest I/O={lowest_io['algorithm']:18} "
            f"fastest={fastest['algorithm']}"
        )


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if DATABASE_DIR.exists():
        shutil.rmtree(DATABASE_DIR)

    results = memory_sweep()
    results.extend(relation_sweep())

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print_summary(results)

    print(f"\nCompleted {len(results)} join executions.")
    print(f"Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
