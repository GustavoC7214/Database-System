"""Experiment 4: Grace hash join under uniform and skewed key distributions.

Run:
    python3 -m experiments.m2.hash_skew

Output:
    experiments/m2/results/hash_skew.csv
"""

import csv
import math
import shutil
import time
from pathlib import Path

from src.execution.grace_hash_join import GraceHashJoin
from src.execution.plan_executor import PhysicalPlanExecutor
from src.execution.temp_run import tuple_size
from src.storage.catalog import Catalog
from src.storage.disk_manager import PAGE_SIZE
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

RESULTS_DIR = Path("experiments/m2/results")
DATABASE_DIR = RESULTS_DIR / "hash_skew_db"
OUTPUT_FILE = RESULTS_DIR / "hash_skew.csv"

LEFT_ROWS = 500
RIGHT_ROWS = 250
SKEW_FRACTION = 0.40
FRAME_BUDGETS = (4, 8, 16, 32)

SCHEMA = "id:INT,join_key:INT,payload:VARCHAR(100)"

FIELDNAMES = (
    "distribution",
    "frames",
    "left_rows",
    "right_rows",
    "output_rows",
    "partition_count",
    "largest_left_partition_rows",
    "largest_right_partition_rows",
    "largest_left_partition_pages",
    "largest_right_partition_pages",
    "predicted_overflow_partitions",
    "actual_overflow_partitions",
    "actual_largest_left_partition_rows",
    "actual_largest_right_partition_rows",
    "actual_largest_left_partition_pages",
    "actual_largest_right_partition_pages",
    "input_page_reads",
    "temp_page_reads",
    "temp_page_writes",
    "total_page_io",
    "io_per_output_row",
    "comparisons",
    "elapsed_seconds",
)


def make_rows(count: int, distribution: str, prefix: str) -> list[tuple]:
    """Generate reproducible uniform or 40%-skewed join keys."""
    skew_count = int(count * SKEW_FRACTION)
    rows = []

    for index in range(count):
        if distribution == "skewed" and index < skew_count:
            key = 0
        else:
            # Uniform workload has unique matching keys.
            # Non-skewed rows never use the hot key.
            key = index + 1

        rows.append(
            (
                index,
                key,
                f"{prefix}_{index:06d}_" + "x" * 60,
            )
        )

    return rows


def create_database(
    path: Path,
    distribution: str,
) -> tuple[list[tuple], list[tuple]]:
    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)
    catalog = Catalog(path)

    left_rows = make_rows(LEFT_ROWS, distribution, "L")
    right_rows = make_rows(RIGHT_ROWS, distribution, "R")

    for table_name, rows in (
        ("SkewLeft", left_rows),
        ("SkewRight", right_rows),
    ):
        metadata = catalog.create_table(table_name, SCHEMA)
        heap = HeapFile(path / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()

    return left_rows, right_rows


def partition_statistics(
    left_rows: list[tuple],
    right_rows: list[tuple],
    frames: int,
) -> dict:
    """Predict partition sizes using the join's actual hash function."""
    partition_count = frames - 1

    left_partitions: list[list[tuple]] = [[] for _ in range(partition_count)]
    right_partitions: list[list[tuple]] = [[] for _ in range(partition_count)]

    for row in left_rows:
        index = GraceHashJoin._partition_index(row[1], partition_count)
        left_partitions[index].append(row)

    for row in right_rows:
        index = GraceHashJoin._partition_index(row[1], partition_count)
        right_partitions[index].append(row)

    # GraceHashJoin adds 64 bytes per tuple when calculating
    # hash-table memory usage.
    memory_limit = (frames - 2) * PAGE_SIZE

    predicted_overflows = 0

    for partition in left_partitions:
        used_bytes = sum(tuple_size(row) + 64 for row in partition)

        if used_bytes > memory_limit:
            predicted_overflows += 1

    # Temporary-page sizes are approximated from serialized tuples.
    # Exact physical page counts can differ due to page packing.
    def estimated_pages(partition: list[tuple]) -> int:
        if not partition:
            return 0

        total_bytes = sum(tuple_size(row) for row in partition)
        return math.ceil(total_bytes / (PAGE_SIZE - 4))

    return {
        "partition_count": partition_count,
        "largest_left_partition_rows": max(
            len(partition) for partition in left_partitions
        ),
        "largest_right_partition_rows": max(
            len(partition) for partition in right_partitions
        ),
        "largest_left_partition_pages": max(
            estimated_pages(partition) for partition in left_partitions
        ),
        "largest_right_partition_pages": max(
            estimated_pages(partition) for partition in right_partitions
        ),
        "predicted_overflow_partitions": predicted_overflows,
    }


def expected_output_count(
    left_rows: list[tuple],
    right_rows: list[tuple],
) -> int:
    left_counts: dict[int, int] = {}
    right_counts: dict[int, int] = {}

    for row in left_rows:
        key = row[1]
        left_counts[key] = left_counts.get(key, 0) + 1

    for row in right_rows:
        key = row[1]
        right_counts[key] = right_counts.get(key, 0) + 1

    return sum(count * right_counts.get(key, 0) for key, count in left_counts.items())


def measure(
    database: Path,
    distribution: str,
    frames: int,
    left_rows: list[tuple],
    right_rows: list[tuple],
) -> dict:
    executor = PhysicalPlanExecutor(database, frames=frames)

    plan = {
        "op": "GraceHashJoin",
        "left_key": "SkewLeft.join_key",
        "right_key": "SkewRight.join_key",
        "left": {"op": "SeqScan", "table": "SkewLeft"},
        "right": {"op": "SeqScan", "table": "SkewRight"},
    }

    root = executor.builder.build(plan)

    if not isinstance(root, GraceHashJoin):
        raise TypeError("Expected a GraceHashJoin root operator")

    started = time.perf_counter()
    result = executor.execute_operator(root)
    elapsed = time.perf_counter() - started

    expected = expected_output_count(left_rows, right_rows)

    if len(result.rows) != expected:
        raise AssertionError(
            f"{distribution} B={frames}: "
            f"expected {expected} rows, got {len(result.rows)}"
        )

    if executor.pages.reserved_frames:
        raise AssertionError("Reserved frames leaked")

    if any(executor.pages.pin_counts):
        raise AssertionError("Pinned frames leaked")

    if result.buffer_stats is None:
        raise RuntimeError("Execution result is missing buffer statistics")

    input_reads = result.buffer_stats["reads"]
    total_reads = result.counters["page_reads"]
    total_writes = result.counters["page_writes"]

    temp_reads = total_reads - input_reads

    if temp_reads < 0:
        raise AssertionError("Inconsistent read counters")

    stats = partition_statistics(left_rows, right_rows, frames)
    total_io = total_reads + total_writes

    return {
        "distribution": distribution,
        "frames": frames,
        "left_rows": len(left_rows),
        "right_rows": len(right_rows),
        "output_rows": len(result.rows),
        **stats,
        "actual_overflow_partitions": root.overflow_partition_count,
        "actual_largest_left_partition_rows": max(root.left_partition_rows, default=0),
        "actual_largest_right_partition_rows": max(
            root.right_partition_rows, default=0
        ),
        "actual_largest_left_partition_pages": max(
            root.left_partition_pages, default=0
        ),
        "actual_largest_right_partition_pages": max(
            root.right_partition_pages, default=0
        ),
        "input_page_reads": input_reads,
        "temp_page_reads": temp_reads,
        "temp_page_writes": total_writes,
        "total_page_io": total_io,
        "io_per_output_row": round(total_io / max(len(result.rows), 1), 6),
        "comparisons": result.counters["comparisons"],
        "elapsed_seconds": round(elapsed, 6),
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for distribution in ("uniform", "skewed"):
        database = DATABASE_DIR / distribution

        left_rows, right_rows = create_database(database, distribution)

        for frames in FRAME_BUDGETS:
            print(
                f"Running {distribution:7} B={frames:3}",
                flush=True,
            )

            measurement = measure(
                database,
                distribution,
                frames,
                left_rows,
                right_rows,
            )

            results.append(measurement)

            print(
                f"  output={measurement['output_rows']:6} "
                f"predicted overflow={measurement['predicted_overflow_partitions']:2} "
                f"actual overflow={measurement['actual_overflow_partitions']:2} "
                f"I/O={measurement['total_page_io']:6} "
                f"time={measurement['elapsed_seconds']:.4f}s",
                flush=True,
            )

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCompleted {len(results)} configurations.")
    print(f"Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
