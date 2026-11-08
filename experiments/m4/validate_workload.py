"""Validate the Module 4 SQL workload against the physical executor."""

import json
from collections import Counter
from pathlib import Path

from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.analyze import analyze_table
from src.optimizer.physical_lowering import (
    UnsupportedPhysicalPlan,
    lower_physical_plan,
)
from src.optimizer.sql_pipeline import compile_optimized_sql
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog

DB_DIR = Path("experiments/m4/results/benchmark_db")
WORKLOAD = Path("experiments/m4/workload.json")

TABLE_COLUMNS = {
    "Customers": ["cid", "region", "tier", "age"],
    "Orders": ["oid", "cid", "amount", "status"],
    "Payments": ["pid", "oid", "method", "amount"],
    "Shipments": ["sid", "oid", "warehouse", "days"],
}

TABLE_ROWS = {
    "Customers": 240,
    "Orders": 960,
    "Payments": 960,
    "Shipments": 960,
}


def load_statistics(
    *,
    refresh: bool = False,
    db_dir: Path = DB_DIR,
) -> dict[str, TableStatistics]:
    """Load or generate ANALYZE statistics for the selected database."""
    store = StatisticsStore(db_dir)
    statistics = {}

    for name in TABLE_COLUMNS:
        stored = None if refresh else store.load(name)

        if stored is None:
            stored = analyze_table(
                db_dir,
                name,
                buckets=20,
                frames=32,
            )

        statistics[name] = stored

    return statistics


def main() -> None:
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    catalog = Catalog(DB_DIR)
    compiler = SQLCompiler(SchemaCatalog(catalog))
    statistics = load_statistics()

    passed = 0
    failed = 0

    for query in workload["queries"]:
        query_id = query["id"]

        try:
            plans = compile_optimized_sql(
                query["sql"],
                compiler,
                statistics,
                table_columns=TABLE_COLUMNS,
                frames=32,
                enable_join_ordering=True,
                enable_logical_rewrites=True,
            )

            if len(plans) != 1:
                raise ValueError(f"Expected one plan, received {len(plans)}")

            physical = lower_physical_plan(
                plans[0],
                statistics,
                table_columns=TABLE_COLUMNS,
                frames=32,
            )

            executor = PhysicalPlanExecutor(DB_DIR, frames=32)
            result = executor.execute(physical)

            # Preserve duplicates when validating query results.
            rows = Counter(map(tuple, result.rows))
            assert sum(rows.values()) == len(result.rows)

            reads = result.buffer_stats["reads"]
            writes = result.buffer_stats["writes"]

            print(
                f"{query_id}: PASS "
                f"rows={len(result.rows)} "
                f"reads={reads} writes={writes}"
            )
            passed += 1

        except (
            UnsupportedPhysicalPlan,
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
        ) as error:
            print(f"{query_id}: FAIL {type(error).__name__}: {error}")
            failed += 1

    print()
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")


if __name__ == "__main__":
    main()
