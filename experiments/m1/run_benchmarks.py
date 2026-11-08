"""Run Module 1 LRU and CLOCK trace benchmarks."""

import csv
from pathlib import Path

from src.storage.trace_runner import read_trace, run_trace

BASE = Path("experiments/m1")
TRACES = (
    "sequential",
    "looping",
    "hotset",
    "phased",
    "random",
)
BUFFER_SIZES = (4, 16, 64, 256)
POLICIES = ("lru", "clock")


def main():
    results_dir = BASE / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    output = results_dir / "buffer_benchmarks.csv"

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            (
                "trace",
                "frames",
                "policy",
                "accesses",
                "hits",
                "misses",
                "evictions",
                "reads",
                "writes",
                "hit_rate_percent",
            )
        )

        count = 0

        for trace_name in TRACES:
            trace_path = BASE / "traces" / f"{trace_name}.txt"
            accesses = len(read_trace(trace_path))

            for frames in BUFFER_SIZES:
                for policy in POLICIES:
                    stats = run_trace(
                        results_dir,
                        trace_path,
                        frames=frames,
                        policy=policy,
                    )

                    hit_rate = 100 * stats["hits"] / accesses

                    writer.writerow(
                        (
                            trace_name,
                            frames,
                            policy,
                            accesses,
                            stats["hits"],
                            stats["misses"],
                            stats["evictions"],
                            stats["reads"],
                            stats["writes"],
                            f"{hit_rate:.2f}",
                        )
                    )

                    count += 1

    print(f"Completed {count} benchmark runs")
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
