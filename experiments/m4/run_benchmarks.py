"""Compare optimized and baseline execution on Module 4 databases."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from experiments.m4.validate_workload import (
    DB_DIR,
    TABLE_COLUMNS,
    WORKLOAD,
    load_statistics,
)
from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.sql_pipeline import compile_optimized_sql
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog

RESULTS_DIR = Path("experiments/m4/results")
FRAMES = 32


def compile_plan(
    sql: str,
    compiler: SQLCompiler,
    statistics: dict,
    *,
    optimized: bool,
) -> dict:
    """Compile and lower a query under one optimization configuration."""
    plans = compile_optimized_sql(
        sql,
        compiler,
        statistics,
        table_columns=TABLE_COLUMNS,
        frames=FRAMES,
        enable_join_ordering=optimized,
        enable_logical_rewrites=optimized,
    )

    if len(plans) != 1:
        raise ValueError(f"Expected one plan, got {len(plans)}")

    return lower_physical_plan(
        plans[0],
        statistics,
        table_columns=TABLE_COLUMNS,
        frames=FRAMES,
        join_algorithm=None if optimized else "nested_loop_join",
        preserve_join_order=not optimized,
    )


def execute_plan(
    plan: dict,
    *,
    db_dir: Path,
) -> tuple[Counter, dict, dict]:
    """Execute and collect result rows, buffer I/O, and operator counters."""
    executor = PhysicalPlanExecutor(db_dir, frames=FRAMES)
    result = executor.execute(plan)

    rows = Counter(map(tuple, result.rows))

    return rows, result.buffer_stats, result.counters


def run_benchmarks(
    *,
    db_dir: Path = DB_DIR,
    output: Path | None = None,
    query_id: str | None = None,
) -> list[dict]:
    """Run comparable optimized and baseline executions."""
    db_dir = Path(db_dir)

    if not db_dir.is_dir():
        raise FileNotFoundError(f"Database directory not found: {db_dir}")

    if output is None:
        suffix = f"_{query_id}" if query_id is not None else ""
        output = RESULTS_DIR / f"benchmark_results_{db_dir.name}{suffix}.csv"

    catalog = Catalog(db_dir)
    compiler = SQLCompiler(SchemaCatalog(catalog))
    statistics = load_statistics(db_dir=db_dir)

    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    queries = workload["queries"]

    if query_id is not None:
        queries = [query for query in queries if query["id"] == query_id]
        if not queries:
            raise ValueError(f"Unknown workload query: {query_id}")

    records = []

    for query in queries:
        current_id = query["id"]

        optimized_plan = compile_plan(
            query["sql"],
            compiler,
            statistics,
            optimized=True,
        )

        baseline_plan = compile_plan(
            query["sql"],
            compiler,
            statistics,
            optimized=False,
        )

        optimized_rows, optimized_io, optimized_counters = execute_plan(
            optimized_plan,
            db_dir=db_dir,
        )
        baseline_rows, baseline_io, baseline_counters = execute_plan(
            baseline_plan,
            db_dir=db_dir,
        )

        if optimized_rows != baseline_rows:
            raise AssertionError(f"{current_id}: optimized and baseline results differ")

        optimized_total = optimized_io["reads"] + optimized_io["writes"]
        baseline_total = baseline_io["reads"] + baseline_io["writes"]

        if optimized_total == 0:
            ratio = 1.0 if baseline_total == 0 else float("inf")
        else:
            ratio = baseline_total / optimized_total

        record = {
            "query": current_id,
            "category": query["category"],
            "rows": sum(optimized_rows.values()),
            "optimized_reads": optimized_io["reads"],
            "optimized_writes": optimized_io["writes"],
            "optimized_io": optimized_total,
            "baseline_reads": baseline_io["reads"],
            "baseline_writes": baseline_io["writes"],
            "baseline_io": baseline_total,
            "baseline_over_optimized": round(ratio, 4),
            "optimized_operator_reads": optimized_counters.get("page_reads", 0),
            "baseline_operator_reads": baseline_counters.get("page_reads", 0),
            "optimized_tuples_in": optimized_counters.get("tuples_in", 0),
            "baseline_tuples_in": baseline_counters.get("tuples_in", 0),
        }

        records.append(record)

        print(
            f"{current_id}: "
            f"rows={record['rows']} "
            f"buffer_io={optimized_total}/{baseline_total} "
            f"operator_reads="
            f"{record['optimized_operator_reads']}/"
            f"{record['baseline_operator_reads']} "
            f"ratio={ratio:.2f}x"
        )

    if records:
        output.parent.mkdir(parents=True, exist_ok=True)

        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(records[0]),
            )
            writer.writeheader()
            writer.writerows(records)

    print(f"\nCompleted {len(records)} benchmarks.")

    if records:
        print(f"Results saved to {output}")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Module 4 optimized/baseline benchmarks."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_DIR,
        help="Database directory to benchmark",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Run one workload query, e.g. Q14",
    )

    args = parser.parse_args()

    run_benchmarks(
        db_dir=args.db,
        output=args.output,
        query_id=args.query,
    )


if __name__ == "__main__":
    main()
