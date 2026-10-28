"""Experiment 2: External merge sort across input sizes and frame budgets.

Run:
    python3 -m experiments.m2.sort_passes

Output:
    experiments/m2/results/sort_passes.csv
"""

import csv
import math
import shutil
import time
from pathlib import Path

from src.execution.plan_executor import PhysicalPlanExecutor
from src.execution.sort import Sort
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

RESULTS_DIR = Path("experiments/m2/results")
DATABASE_DIR = RESULTS_DIR / "sort_passes_db"

# (label, target data pages, buffer frames)
CONFIGURATIONS = (
    ("n8_b4", 8, 4),
    ("n20_b4", 20, 4),
    ("n40_b4", 40, 4),
    ("n80_b4", 80, 4),  # Required N = 20B
    ("n80_b8", 80, 8),
    ("n80_b16", 80, 16),
    ("n80_b32", 80, 32),
)

SCHEMA = "id:INT,sort_key:INT,payload:VARCHAR(100)"
TABLE_NAME = "SortBench"

FIELDNAMES = (
    "configuration",
    "target_data_pages",
    "actual_data_pages",
    "frames",
    "rows",
    "initial_runs_theoretical",
    "merge_passes_theoretical",
    "total_passes_theoretical",
    "initial_runs_actual",
    "intermediate_merge_passes_actual",
    "final_merge_passes_actual",
    "merge_passes_actual",
    "total_passes_actual",
    "input_page_reads",
    "temp_page_reads",
    "temp_page_writes",
    "total_page_reads",
    "total_page_writes",
    "total_page_io",
    "comparisons",
    "elapsed_seconds",
)


def create_database(path: Path, target_pages: int) -> tuple[int, int]:
    """Generate a relation with exactly target_pages data pages."""
    from src.storage.disk_manager import PAGE_SIZE

    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)
    catalog = Catalog(path)
    metadata = catalog.create_table(TABLE_NAME, SCHEMA)
    heap = HeapFile(path / metadata.filename)

    row_count = 0
    table_path = path / metadata.filename

    while True:
        # Fixed-width payload ensures repeatable row sizes.
        row = (
            row_count,
            -row_count,
            f"row_{row_count:08d}_" + "x" * 60,
        )

        heap.insert(encode_record(row, metadata.schema))
        row_count += 1
        heap.flush()

        physical_pages = table_path.stat().st_size // PAGE_SIZE
        data_pages = physical_pages - 1

        if data_pages >= target_pages:
            break

    if data_pages != target_pages:
        raise AssertionError(f"Expected {target_pages} data pages, got {data_pages}")

    return row_count, data_pages


def theoretical_passes(
    data_pages: int,
    frames: int,
) -> tuple[int, int, int]:
    """Calculate textbook B-frame external merge-sort pass counts."""
    initial_runs = math.ceil(data_pages / frames)

    merge_passes = 0
    remaining_runs = initial_runs
    fan_in = frames - 1

    while remaining_runs > 1:
        remaining_runs = math.ceil(remaining_runs / fan_in)
        merge_passes += 1

    return initial_runs, merge_passes, 1 + merge_passes


def measure(
    database: Path,
    label: str,
    target_pages: int,
    actual_pages: int,
    frames: int,
    expected_rows: int,
) -> dict:
    executor = PhysicalPlanExecutor(database, frames=frames)

    plan = {
        "op": "Sort",
        "keys": [["SortBench.sort_key", "ASC"]],
        "child": {"op": "SeqScan", "table": TABLE_NAME},
    }

    # Build the operator explicitly so its actual pass counts remain
    # accessible after execution. The executor still handles opening,
    # consuming, closing, and collecting statistics normally.
    root = executor.builder.build(plan)

    if not isinstance(root, Sort):
        raise TypeError(f"{label}: expected a Sort root operator")

    started = time.perf_counter()
    result = executor.execute_operator(root)
    elapsed = time.perf_counter() - started

    if len(result.rows) != expected_rows:
        raise AssertionError(
            f"{label}: expected {expected_rows} rows, got {len(result.rows)}"
        )

    actual_keys = [row[1] for row in result.rows]
    expected_keys = list(range(-(expected_rows - 1), 1))

    if actual_keys != expected_keys:
        raise AssertionError(f"{label}: incorrect sort order")

    if executor.pages.reserved_frames:
        raise AssertionError(f"{label}: reserved frames leaked")

    if any(executor.pages.pin_counts):
        raise AssertionError(f"{label}: pinned frames leaked")

    if result.buffer_stats is None:
        raise RuntimeError("Execution result is missing buffer statistics")

    input_reads = result.buffer_stats["reads"]
    total_reads = result.counters["page_reads"]
    total_writes = result.counters["page_writes"]

    temp_reads = total_reads - input_reads

    if temp_reads < 0:
        raise AssertionError(f"{label}: inconsistent read counters")

    initial_runs, merge_passes, total_passes = theoretical_passes(actual_pages, frames)

    actual_initial_runs = root.initial_run_count
    actual_intermediate_passes = root.intermediate_merge_passes
    actual_final_passes = root.final_merge_passes

    actual_merge_passes = actual_intermediate_passes + actual_final_passes

    # Initial run generation is one logical pass for nonempty input.
    actual_total_passes = 1 + actual_merge_passes if actual_initial_runs else 0

    return {
        "configuration": label,
        "target_data_pages": target_pages,
        "actual_data_pages": actual_pages,
        "frames": frames,
        "rows": expected_rows,
        "initial_runs_theoretical": initial_runs,
        "merge_passes_theoretical": merge_passes,
        "total_passes_theoretical": total_passes,
        "initial_runs_actual": actual_initial_runs,
        "intermediate_merge_passes_actual": actual_intermediate_passes,
        "final_merge_passes_actual": actual_final_passes,
        "merge_passes_actual": actual_merge_passes,
        "total_passes_actual": actual_total_passes,
        "input_page_reads": input_reads,
        "temp_page_reads": temp_reads,
        "temp_page_writes": total_writes,
        "total_page_reads": total_reads,
        "total_page_writes": total_writes,
        "total_page_io": total_reads + total_writes,
        "comparisons": result.counters["comparisons"],
        "elapsed_seconds": round(elapsed, 6),
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for label, target_pages, frames in CONFIGURATIONS:
        database = DATABASE_DIR / label

        row_count, actual_pages = create_database(database, target_pages)

        print(
            f"Running {label:10} "
            f"target N={target_pages:3} "
            f"actual N={actual_pages:3} "
            f"B={frames:3}",
            flush=True,
        )

        measurement = measure(
            database,
            label,
            target_pages,
            actual_pages,
            frames,
            row_count,
        )

        results.append(measurement)

        print(
            f"  theoretical runs={measurement['initial_runs_theoretical']:3} "
            f"actual runs={measurement['initial_runs_actual']:3} "
            f"theoretical merges={measurement['merge_passes_theoretical']:2} "
            f"actual merges={measurement['merge_passes_actual']:2} "
            f"I/O={measurement['total_page_io']:6} "
            f"time={measurement['elapsed_seconds']:.4f}s",
            flush=True,
        )

    output = RESULTS_DIR / "sort_passes.csv"

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCompleted {len(results)} configurations.")
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
