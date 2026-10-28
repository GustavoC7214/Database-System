"""Generate crossover plots from recorded Module 2 benchmark results."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parent / "results"
INPUT_CSV = RESULTS_DIR / "join_crossover.csv"

ALGORITHMS = {
    "NestedLoopJoin": "Block Nested-Loop Join",
    "SortMergeJoin": "Sort-Merge Join",
    "GraceHashJoin": "Grace Hash Join",
}

STYLES = {
    "NestedLoopJoin": {"marker": "o", "linestyle": "-"},
    "SortMergeJoin": {"marker": "s", "linestyle": "--"},
    "GraceHashJoin": {"marker": "^", "linestyle": "-."},
}


def load_results() -> list[dict]:
    """Load benchmark rows with their recorded numeric values."""
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Missing benchmark results: {INPUT_CSV}")

    with INPUT_CSV.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    required = {
        "sweep",
        "algorithm",
        "frames",
        "left_rows",
        "right_rows",
        "elapsed_seconds",
        "total_page_io",
    }

    if not rows:
        raise ValueError("The benchmark CSV contains no results")

    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing CSV columns: {sorted(missing)}")

    for row in rows:
        row["frames"] = int(row["frames"])
        row["left_rows"] = int(row["left_rows"])
        row["right_rows"] = int(row["right_rows"])
        row["elapsed_seconds"] = float(row["elapsed_seconds"])
        row["total_page_io"] = int(row["total_page_io"])

    return rows


def plot_memory_crossover(rows: list[dict]) -> None:
    """Compare join execution times as the shared frame budget changes."""
    selected = [
        row
        for row in rows
        if row["sweep"] == "memory"
        and row["left_rows"] == 2000
        and row["right_rows"] == 1000
    ]

    if not selected:
        raise ValueError("No memory-crossover results were found")

    fig, ax = plt.subplots(figsize=(9, 5.5))

    for algorithm, label in ALGORITHMS.items():
        points = sorted(
            (row for row in selected if row["algorithm"] == algorithm),
            key=lambda row: row["frames"],
        )

        if not points:
            raise ValueError(f"No memory results for {algorithm}")

        ax.plot(
            [row["frames"] for row in points],
            [row["elapsed_seconds"] for row in points],
            label=label,
            linewidth=2,
            markersize=6,
            **STYLES[algorithm],
        )

    ax.set_xscale("log", base=2)
    ax.set_xticks(sorted({row["frames"] for row in selected}))
    ax.set_xticklabels(
        [str(value) for value in sorted({row["frames"] for row in selected})]
    )

    ax.set_xlabel("Shared Buffer Frames (B)")
    ax.set_ylabel("Execution Time (seconds)")
    ax.set_title(
        "Join Algorithm Crossover by Buffer Budget\n"
        "Left: 2,000 tuples | Right: 1,000 tuples"
    )

    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    output = RESULTS_DIR / "join_crossover_memory.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Created: {output}")


def plot_size_crossover(rows: list[dict]) -> None:
    """Compare join execution times as input relation sizes increase."""
    selected = [
        row for row in rows if row["sweep"] == "relation" and row["frames"] == 16
    ]

    if not selected:
        raise ValueError("No relation-size crossover results were found")

    fig, ax = plt.subplots(figsize=(9, 5.5))

    for algorithm, label in ALGORITHMS.items():
        points = sorted(
            (row for row in selected if row["algorithm"] == algorithm),
            key=lambda row: row["left_rows"],
        )

        if not points:
            raise ValueError(f"No size results for {algorithm}")

        ax.plot(
            [row["left_rows"] for row in points],
            [row["elapsed_seconds"] for row in points],
            label=label,
            linewidth=2,
            markersize=6,
            **STYLES[algorithm],
        )

    ax.set_xlabel("Left Relation Size (tuples)")
    ax.set_ylabel("Execution Time (seconds)")
    ax.set_title(
        "Join Algorithm Crossover by Relation Size\n"
        "Right relation = 0.5 × left relation | B = 16"
    )

    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    output = RESULTS_DIR / "join_crossover_size.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Created: {output}")


def main() -> None:
    rows = load_results()
    plot_memory_crossover(rows)
    plot_size_crossover(rows)


if __name__ == "__main__":
    main()
