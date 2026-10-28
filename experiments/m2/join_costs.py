"""Experiment 1: Compare physical join costs across memory budgets.

Run:
    python3 -m experiments.m2.join_costs

Output:
    experiments/m2/results/join_costs.csv
"""

import csv
import time
from pathlib import Path

from src.execution.plan_executor import PhysicalPlanExecutor
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

RESULTS_DIR = Path("experiments/m2/results")
DATABASE_DIR = RESULTS_DIR / "join_costs_db"

FRAME_BUDGETS = (4, 16, 64, 256)

# (label, left row count, right row count)
RELATION_SIZES = (
    ("small", 100, 50),
    ("medium", 500, 250),
    ("large", 2000, 1000),
)

ALGORITHMS = (
    "NestedLoopJoin",
    "SortMergeJoin",
    "GraceHashJoin",
)

FIELDNAMES = (
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


def create_database(
    path: Path,
    left_count: int,
    right_count: int,
) -> None:
    """Create reproducible disk-backed relations."""
    path.mkdir(parents=True, exist_ok=True)
    catalog = Catalog(path)

    tables = (
        (
            "BenchLeft",
            "id:INT,join_key:INT,payload:VARCHAR(100)",
            (
                (index, index, f"L_{index:06d}_" + "x" * 60)
                for index in range(left_count)
            ),
        ),
        (
            "BenchRight",
            "id:INT,join_key:INT,payload:VARCHAR(100)",
            (
                (index, index, f"R_{index:06d}_" + "y" * 60)
                for index in range(right_count)
            ),
        ),
    )

    for name, schema, rows in tables:
        metadata = catalog.create_table(name, schema)
        heap = HeapFile(path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()


def build_plan(algorithm: str) -> dict:
    return {
        "op": algorithm,
        "left_key": "BenchLeft.join_key",
        "right_key": "BenchRight.join_key",
        "left": {"op": "SeqScan", "table": "BenchLeft"},
        "right": {"op": "SeqScan", "table": "BenchRight"},
    }


def measure(
    database: Path,
    algorithm: str,
    frames: int,
    size: str,
    left_count: int,
    right_count: int,
) -> dict:
    executor = PhysicalPlanExecutor(database, frames=frames)

    started = time.perf_counter()
    result = executor.execute(build_plan(algorithm))
    elapsed = time.perf_counter() - started

    expected_matches = min(left_count, right_count)

    if len(result.rows) != expected_matches:
        raise AssertionError(
            f"{algorithm} B={frames}: expected {expected_matches} "
            f"rows, got {len(result.rows)}"
        )

    actual_keys = sorted(row[1] for row in result.rows)
    expected_keys = list(range(expected_matches))

    if actual_keys != expected_keys:
        raise AssertionError(f"{algorithm} B={frames}: incorrect join results")

    if executor.pages.reserved_frames:
        raise AssertionError(f"{algorithm} B={frames}: reserved frames leaked")

    if any(executor.pages.pin_counts):
        raise AssertionError(f"{algorithm} B={frames}: pinned frames leaked")

    if result.buffer_stats is None:
        raise RuntimeError("Execution result is missing buffer statistics")

    if result.buffer_stats is None:
        raise RuntimeError("Execution result is missing buffer statistics")

    input_reads = result.buffer_stats["reads"]

    # Operator totals already include SeqScan's physical page reads.
    # Subtract those reads to isolate temporary-file activity.
    total_reads = result.counters["page_reads"]
    total_writes = result.counters["page_writes"]

    temp_reads = total_reads - input_reads
    temp_writes = total_writes

    if temp_reads < 0:
        raise AssertionError(
            "Operator page-read totals are smaller than physical input reads"
        )

    return {
        "size": size,
        "algorithm": algorithm,
        "frames": frames,
        "left_rows": left_count,
        "right_rows": right_count,
        "output_rows": len(result.rows),
        "input_page_reads": input_reads,
        "temp_page_reads": temp_reads,
        "temp_page_writes": temp_writes,
        "total_page_reads": total_reads,
        "total_page_writes": total_writes,
        "total_page_io": total_reads + total_writes,
        "comparisons": result.counters["comparisons"],
        "elapsed_seconds": round(elapsed, 6),
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for size, left_count, right_count in RELATION_SIZES:
        database = DATABASE_DIR / size

        create_database(database, left_count, right_count)

        for frames in FRAME_BUDGETS:
            for algorithm in ALGORITHMS:
                print(
                    f"Running {size:6} B={frames:3} {algorithm:18}",
                    flush=True,
                )

                measurement = measure(
                    database,
                    algorithm,
                    frames,
                    size,
                    left_count,
                    right_count,
                )

                results.append(measurement)

                print(
                    f"  I/O={measurement['total_page_io']:6} "
                    f"comparisons={measurement['comparisons']:8} "
                    f"time={measurement['elapsed_seconds']:.4f}s",
                    flush=True,
                )

    output = RESULTS_DIR / "join_costs.csv"

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCompleted {len(results)} configurations.")
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
