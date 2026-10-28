"""Experiment 5: External sort under a strict four-frame memory budget.

Run:
    python3 -m experiments.m2.memory_stress

Output:
    experiments/m2/results/memory_stress.csv
"""

import csv
import time
from unittest.mock import patch

from experiments.m2.sort_passes import (
    RESULTS_DIR,
    TABLE_NAME,
    create_database,
    theoretical_passes,
)
from src.execution.page_manager import SharedPageManager
from src.execution.plan_executor import PhysicalPlanExecutor

DATABASE_DIR = RESULTS_DIR / "memory_stress_db"
OUTPUT_FILE = RESULTS_DIR / "memory_stress.csv"

TARGET_PAGES = 80
FRAME_BUDGET = 4

FIELDNAMES = (
    "input_data_pages",
    "buffer_frames",
    "input_to_buffer_ratio",
    "rows",
    "initial_runs_theoretical",
    "merge_passes_theoretical",
    "peak_reserved_frames",
    "peak_cached_frames",
    "peak_occupied_frames",
    "peak_pinned_frames",
    "final_reserved_frames",
    "final_pinned_frames",
    "total_page_reads",
    "total_page_writes",
    "total_page_io",
    "elapsed_seconds",
    "sorted_correctly",
    "memory_budget_respected",
)


class FrameMonitor:
    """Observe shared-frame occupancy throughout query execution."""

    def __init__(self) -> None:
        self.peak_reserved = 0
        self.peak_cached = 0
        self.peak_occupied = 0
        self.peak_pinned = 0
        self.samples = 0

    def sample(self, manager: SharedPageManager) -> None:
        reserved = set(manager.reserved_frames)
        cached = set(manager.page_table.values())

        pinned = {index for index, count in enumerate(manager.pin_counts) if count > 0}

        occupied = reserved | cached | pinned

        if len(occupied) > manager.capacity:
            raise AssertionError(
                f"Frame budget exceeded: {len(occupied)} > {manager.capacity}"
            )

        if reserved & cached:
            raise AssertionError("A frame is simultaneously reserved and cached")

        if reserved & pinned:
            raise AssertionError("A frame is simultaneously reserved and pinned")

        self.peak_reserved = max(self.peak_reserved, len(reserved))
        self.peak_cached = max(self.peak_cached, len(cached))
        self.peak_occupied = max(self.peak_occupied, len(occupied))
        self.peak_pinned = max(self.peak_pinned, len(pinned))
        self.samples += 1


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Creating exact 80-page relation...", flush=True)

    row_count, actual_pages = create_database(
        DATABASE_DIR,
        TARGET_PAGES,
    )

    if actual_pages != TARGET_PAGES:
        raise AssertionError(f"Expected {TARGET_PAGES} pages, got {actual_pages}")

    if actual_pages != 20 * FRAME_BUDGET:
        raise AssertionError("N = 20B requirement not satisfied")

    executor = PhysicalPlanExecutor(
        DATABASE_DIR,
        frames=FRAME_BUDGET,
    )

    manager = executor.pages
    monitor = FrameMonitor()

    original_reserve = SharedPageManager.reserve_frames
    original_release = SharedPageManager.release_frames
    original_read = SharedPageManager.read_page
    original_pin = SharedPageManager.pin_page
    original_unpin = SharedPageManager.unpin_page

    def monitored_reserve(
        self: SharedPageManager,
        count: int,
    ) -> list[int]:
        result = original_reserve(self, count)
        monitor.sample(self)
        return result

    def monitored_release(
        self: SharedPageManager,
        indices: list[int],
    ) -> None:
        original_release(self, indices)
        monitor.sample(self)

    def monitored_read(self: SharedPageManager, key):
        result = original_read(self, key)
        monitor.sample(self)
        return result

    def monitored_pin(self: SharedPageManager, key) -> None:
        original_pin(self, key)
        monitor.sample(self)

    def monitored_unpin(self: SharedPageManager, key) -> None:
        original_unpin(self, key)
        monitor.sample(self)

    plan = {
        "op": "Sort",
        "keys": [["SortBench.sort_key", "ASC"]],
        "child": {"op": "SeqScan", "table": TABLE_NAME},
    }

    print(
        f"Running external sort: N={actual_pages}, "
        f"B={FRAME_BUDGET}, N/B={actual_pages // FRAME_BUDGET}",
        flush=True,
    )

    monitor.sample(manager)

    started = time.perf_counter()

    with (
        patch.object(
            SharedPageManager,
            "reserve_frames",
            monitored_reserve,
        ),
        patch.object(
            SharedPageManager,
            "release_frames",
            monitored_release,
        ),
        patch.object(
            SharedPageManager,
            "read_page",
            monitored_read,
        ),
        patch.object(
            SharedPageManager,
            "pin_page",
            monitored_pin,
        ),
        patch.object(
            SharedPageManager,
            "unpin_page",
            monitored_unpin,
        ),
    ):
        result = executor.execute(plan)

    elapsed = time.perf_counter() - started

    monitor.sample(manager)

    if len(result.rows) != row_count:
        raise AssertionError(f"Expected {row_count} rows, got {len(result.rows)}")

    actual_keys = [row[1] for row in result.rows]
    expected_keys = list(range(-(row_count - 1), 1))

    sorted_correctly = actual_keys == expected_keys

    if not sorted_correctly:
        raise AssertionError("Sort produced incorrect output")

    if manager.reserved_frames:
        raise AssertionError("Temporary frames leaked")

    if any(manager.pin_counts):
        raise AssertionError("Pinned frames leaked")

    if monitor.samples == 0:
        raise AssertionError("No frame observations were collected")

    if monitor.peak_occupied > FRAME_BUDGET:
        raise AssertionError("Memory budget exceeded")

    initial_runs, merge_passes, _ = theoretical_passes(
        actual_pages,
        FRAME_BUDGET,
    )

    total_reads = result.counters["page_reads"]
    total_writes = result.counters["page_writes"]

    measurement = {
        "input_data_pages": actual_pages,
        "buffer_frames": FRAME_BUDGET,
        "input_to_buffer_ratio": actual_pages / FRAME_BUDGET,
        "rows": row_count,
        "initial_runs_theoretical": initial_runs,
        "merge_passes_theoretical": merge_passes,
        "peak_reserved_frames": monitor.peak_reserved,
        "peak_cached_frames": monitor.peak_cached,
        "peak_occupied_frames": monitor.peak_occupied,
        "peak_pinned_frames": monitor.peak_pinned,
        "final_reserved_frames": len(manager.reserved_frames),
        "final_pinned_frames": sum(manager.pin_counts),
        "total_page_reads": total_reads,
        "total_page_writes": total_writes,
        "total_page_io": total_reads + total_writes,
        "elapsed_seconds": round(elapsed, 6),
        "sorted_correctly": sorted_correctly,
        "memory_budget_respected": monitor.peak_occupied <= FRAME_BUDGET,
    }

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter[str](
            file,
            fieldnames=list(FIELDNAMES),
        )
        writer.writeheader()
        writer.writerow(measurement)

    print("\nMEMORY STRESS TEST RESULTS")
    print("-" * 55)
    print(f"Input data pages:       {actual_pages}")
    print(f"Buffer budget:          {FRAME_BUDGET}")
    print(f"Input rows:             {row_count}")
    print(f"Theoretical runs:       {initial_runs}")
    print(f"Theoretical merges:     {merge_passes}")
    print(f"Peak reserved frames:   {monitor.peak_reserved}")
    print(f"Peak cached frames:     {monitor.peak_cached}")
    print(f"Peak occupied frames:   {monitor.peak_occupied}")
    print(f"Peak pinned frames:     {monitor.peak_pinned}")
    print(f"Final reserved frames:  {len(manager.reserved_frames)}")
    print(f"Final pinned frames:    {sum(manager.pin_counts)}")
    print(f"Frame observations:     {monitor.samples}")
    print(f"Total page I/O:         {total_reads + total_writes}")
    print(f"Elapsed time:           {elapsed:.4f}s")
    print(f"Sorted correctly:       {sorted_correctly}")
    print(f"Memory budget respected: {monitor.peak_occupied <= FRAME_BUDGET}")

    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
