"""Benchmark a correlated-column cardinality estimation failure."""

import argparse
import csv
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.cardinality import estimate_pages
from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.statistics import StatisticsStore

DEFAULT_DB = Path("experiments/m4/results/correlated_db")
DEFAULT_OUTPUT = Path("experiments/m4/results/correlation_failure.csv")

TABLES = ("CorrelatedCustomers", "CorrelatedOrders")

COLUMNS = {
    "CorrelatedCustomers": ["cid", "region", "tier", "age"],
    "CorrelatedOrders": ["oid", "cid", "amount", "status"],
}

FILTER = "CorrelatedCustomers.region = 1 AND CorrelatedCustomers.tier = 1"

ACTUAL_FILTERED_ROWS = 2500


def logical_plan():
    return {
        "op": "join",
        "condition": ("CorrelatedCustomers.cid = CorrelatedOrders.cid"),
        "left": {
            "op": "select",
            "condition": FILTER,
            "child": {
                "op": "scan",
                "table": "CorrelatedCustomers",
            },
        },
        "right": {
            "op": "scan",
            "table": "CorrelatedOrders",
        },
    }


def corrected_estimator(original):
    def estimate(self, plan):
        result = original(self, plan)

        if plan.get("op") == "select" and plan.get("condition") == FILTER:
            return replace(
                result,
                rows=ACTUAL_FILTERED_ROWS,
                pages=estimate_pages(
                    ACTUAL_FILTERED_ROWS,
                    result.width,
                ),
            )

        return result

    return estimate


def benchmark(db: Path, output: Path) -> None:
    stats = {table: StatisticsStore(db).load(table) for table in TABLES}

    logical = logical_plan()

    estimator = LogicalPlanEstimator(
        stats,
        table_columns=COLUMNS,
    )

    filtered = logical["left"]
    estimated_rows = estimator.estimate(filtered).rows

    print(f"Estimated filtered rows: {estimated_rows}")
    print(f"Actual filtered rows: {ACTUAL_FILTERED_ROWS}")
    print(
        "Cardinality q-error:",
        round(
            max(
                estimated_rows / ACTUAL_FILTERED_ROWS,
                ACTUAL_FILTERED_ROWS / estimated_rows,
            ),
            4,
        ),
    )

    original_method = LogicalPlanEstimator.estimate
    corrected_method = corrected_estimator(original_method)

    results = []
    reference_rows = None

    for frames in (4, 8, 16, 32):
        original_plan = lower_physical_plan(
            logical,
            stats,
            table_columns=COLUMNS,
            frames=frames,
        )

        with patch.object(
            LogicalPlanEstimator,
            "estimate",
            corrected_method,
        ):
            corrected_plan = lower_physical_plan(
                logical,
                stats,
                table_columns=COLUMNS,
                frames=frames,
            )

        plans = {
            "original": original_plan,
            "corrected": corrected_plan,
        }

        for variant, physical in plans.items():
            execution = PhysicalPlanExecutor(
                db,
                frames=frames,
            ).execute(physical)

            rows = Counter(execution.rows)

            if reference_rows is None:
                reference_rows = rows
            elif rows != reference_rows:
                raise AssertionError(f"Result mismatch: {variant}, frames={frames}")

            buffer = execution.buffer_stats or {}

            record = {
                "frames": frames,
                "variant": variant,
                "algorithm": physical["op"],
                "output_rows": len(execution.rows),
                "buffer_reads": buffer.get("reads", 0),
                "buffer_writes": buffer.get("writes", 0),
                "operator_page_reads": execution.counters["page_reads"],
                "operator_page_writes": execution.counters["page_writes"],
            }

            results.append(record)

            print(
                f"frames={frames:<2} "
                f"{variant:<10} "
                f"{physical['op']:<18} "
                f"rows={len(execution.rows):<6} "
                f"reads={record['buffer_reads']:<6} "
                f"writes={record['buffer_writes']}"
            )

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open(
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

    print(f"\nSaved results: {output}")
    print("All execution results match.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    benchmark(args.db, args.output)


if __name__ == "__main__":
    main()
