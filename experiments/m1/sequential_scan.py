
"""Benchmark sequential heap scans with different buffer sizes."""

import csv
from pathlib import Path

from src.storage.heap_file import HeapFile

RESULTS_DIR = Path("experiments/m1/results")
DB_PATH = RESULTS_DIR / "sequential_scan.db"

DATA_PAGES = 500
RECORD = b"x" * 4084
BUFFER_SIZES = (2, 8, 64)
POLICIES = ("lru", "clock")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Rebuild the test database for reproducible results.
    DB_PATH.unlink(missing_ok=True)

    heap = HeapFile(DB_PATH, frames=8)

    for _ in range(DATA_PAGES):
        heap.insert(RECORD)

    heap.flush()

    assert heap.page_count == DATA_PAGES + 1

    print(f"Created heap with {DATA_PAGES} data pages")

    output = RESULTS_DIR / "sequential_scan.csv"

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            (
                "policy",
                "frames",
                "records",
                "hits",
                "misses",
                "evictions",
                "reads",
                "writes",
            )
        )

        for policy in POLICIES:
            for frames in BUFFER_SIZES:
                scan_heap = HeapFile(
                    DB_PATH,
                    frames=frames,
                    policy=policy,
                )

                before = scan_heap.buffer.stats()

                record_count = sum(
                    1 for _ in scan_heap.scan()
                )

                after = scan_heap.buffer.stats()

                stats = {
                    key: after[key] - before[key]
                    for key in before
                }

                assert record_count == DATA_PAGES

                writer.writerow(
                    (
                        policy,
                        frames,
                        record_count,
                        stats["hits"],
                        stats["misses"],
                        stats["evictions"],
                        stats["reads"],
                        stats["writes"],
                    )
                )

                print(
                    f"{policy.upper():5} B={frames:2} "
                    f"records={record_count} "
                    f"hits={stats['hits']} "
                    f"misses={stats['misses']} "
                    f"evictions={stats['evictions']} "
                    f"reads={stats['reads']} "
                    f"writes={stats['writes']}"
                )

    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
