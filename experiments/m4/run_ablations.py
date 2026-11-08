"""Run Module 4 optimizer ablation experiments."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from experiments.m4.run_benchmarks import FRAMES, RESULTS_DIR
from experiments.m4.validate_workload import (
    DB_DIR,
    TABLE_COLUMNS,
    WORKLOAD,
    load_statistics,
)
from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.pipeline import optimize_logical_plan
from src.optimizer.sql_join_order import optimize_sql_join_order
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog

CONFIGURATIONS = {
    "fully_optimized": {},
    "no_selection_rewrites": {
        "enable_selection_rewrites": False,
    },
    "no_projection_pushdown": {
        "enable_projection_pushdown": False,
    },
    "no_projection_cleanup": {
        "enable_projection_cleanup": False,
    },
    "no_join_ordering": {
        "enable_join_ordering": False,
    },
}


def build_plan(
    logical_plan: dict,
    table_statistics: dict,
    *,
    configuration: dict,
) -> dict:
    """Apply enabled optimizations and lower the resulting plan."""
    options = dict(configuration)
    join_ordering = options.pop("enable_join_ordering", True)

    rewritten = optimize_logical_plan(
        logical_plan,
        table_columns=TABLE_COLUMNS,
        **options,
    )

    if join_ordering:
        rewritten = optimize_sql_join_order(
            rewritten,
            table_statistics,
            table_columns=TABLE_COLUMNS,
            frames=FRAMES,
        )

    return lower_physical_plan(
        rewritten,
        table_statistics,
        table_columns=TABLE_COLUMNS,
        frames=FRAMES,
    )


def execute_plan(plan: dict, db_dir: Path) -> tuple[Counter, dict, dict]:
    """Execute a plan using a fresh buffer pool."""
    executor = PhysicalPlanExecutor(db_dir, frames=FRAMES)
    result = executor.execute(plan)

    rows = Counter(map(tuple, result.rows))

    return rows, result.buffer_stats, result.counters


def run_ablations(
    *,
    db_dir: Path = DB_DIR,
    output: Path | None = None,
    query_id: str | None = None,
) -> list[dict]:
    db_dir = Path(db_dir)

    if not db_dir.is_dir():
        raise FileNotFoundError(f"Database directory not found: {db_dir}")

    if output is None:
        suffix = f"_{query_id}" if query_id else ""
        output = RESULTS_DIR / f"ablation_{db_dir.name}{suffix}.csv"

    catalog = Catalog(db_dir)
    compiler = SQLCompiler(SchemaCatalog(catalog))
    table_statistics = load_statistics(db_dir=db_dir)

    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    queries = workload["queries"]

    if query_id is not None:
        queries = [query for query in queries if query["id"] == query_id]
        if not queries:
            raise ValueError(f"Unknown query: {query_id}")

    records = []

    for query in queries:
        logical_plans = compiler.compile_sql(query["sql"])

        if len(logical_plans) != 1:
            raise ValueError(f"{query['id']}: expected one logical plan")

        logical_plan = logical_plans[0]
        reference_rows = None

        for name, configuration in CONFIGURATIONS.items():
            physical_plan = build_plan(
                logical_plan,
                table_statistics,
                configuration=configuration,
            )

            rows, buffer_stats, counters = execute_plan(
                physical_plan,
                db_dir,
            )

            if reference_rows is None:
                reference_rows = rows
            elif rows != reference_rows:
                raise AssertionError(f"{query['id']}: {name} changed query results")

            total_io = buffer_stats["reads"] + buffer_stats["writes"]

            records.append(
                {
                    "query": query["id"],
                    "configuration": name,
                    "rows": sum(rows.values()),
                    "buffer_reads": buffer_stats["reads"],
                    "buffer_writes": buffer_stats["writes"],
                    "total_io": total_io,
                    "operator_reads": counters.get("page_reads", 0),
                    "tuples_in": counters.get("tuples_in", 0),
                }
            )

        print(f"{query['id']}: {len(CONFIGURATIONS)} configurations passed")

    if records:
        output.parent.mkdir(parents=True, exist_ok=True)

        with output.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(records[0]),
            )
            writer.writeheader()
            writer.writerows(records)

        print("\nAblation totals")
        print(f"{'Configuration':<27}{'Buffer I/O':>12}{'Operator reads':>18}")

        for name in CONFIGURATIONS:
            selected = [record for record in records if record["configuration"] == name]

            total_io = sum(record["total_io"] for record in selected)
            operator_reads = sum(record["operator_reads"] for record in selected)

            print(f"{name:<27}{total_io:>12}{operator_reads:>18}")

        print(f"\nResults saved to {output}")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Module 4 optimizer ablation experiments."
    )
    parser.add_argument("--db", type=Path, default=DB_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--query", type=str, default=None)

    args = parser.parse_args()

    run_ablations(
        db_dir=args.db,
        output=args.output,
        query_id=args.query,
    )


if __name__ == "__main__":
    main()
