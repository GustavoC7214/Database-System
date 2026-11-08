"""Measure estimated versus actual cardinalities for Module 4 plans."""

import argparse
import csv
import json
import statistics as summary_statistics
from pathlib import Path
from typing import Any

from experiments.m4.run_benchmarks import FRAMES
from experiments.m4.validate_workload import (
    DB_DIR,
    TABLE_COLUMNS,
    WORKLOAD,
    load_statistics,
)
from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.estimator import LogicalPlanEstimator
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.sql_pipeline import compile_optimized_sql
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog

RESULTS_DIR = Path("experiments/m4/results")


def q_error(estimated: int, actual: int) -> float:
    """Calculate q-error, using a floor of one for zero cardinalities."""
    if estimated < 0 or actual < 0:
        raise ValueError("Cardinalities cannot be negative")

    estimated_safe = max(1, estimated)
    actual_safe = max(1, actual)

    return max(
        estimated_safe / actual_safe,
        actual_safe / estimated_safe,
    )


def iter_nodes(
    plan: dict[str, Any],
    path: str = "root",
):
    """Yield every node in a logical plan with its structural path."""
    yield path, plan

    for side in ("child", "left", "right"):
        child = plan.get(side)

        if isinstance(child, dict):
            yield from iter_nodes(child, f"{path}.{side}")


def measure_node(
    plan: dict[str, Any],
    *,
    db_dir: Path,
    table_statistics: dict,
) -> int:
    """Execute one logical subtree and count its output rows."""
    physical_plan = lower_physical_plan(
        plan,
        table_statistics,
        table_columns=TABLE_COLUMNS,
        frames=FRAMES,
    )

    executor = PhysicalPlanExecutor(db_dir, frames=FRAMES)
    result = executor.execute(physical_plan)

    return len(result.rows)


def measure_workload(
    *,
    db_dir: Path = DB_DIR,
    output: Path | None = None,
    query_id: str | None = None,
) -> list[dict[str, Any]]:
    """Measure cardinality estimates at every logical plan node."""
    db_dir = Path(db_dir)

    if not db_dir.is_dir():
        raise FileNotFoundError(f"Database directory not found: {db_dir}")

    if output is None:
        suffix = f"_{query_id}" if query_id else ""
        output = RESULTS_DIR / f"cardinality_{db_dir.name}{suffix}.csv"

    catalog = Catalog(db_dir)
    compiler = SQLCompiler(SchemaCatalog(catalog))
    table_statistics = load_statistics(db_dir=db_dir)

    estimator = LogicalPlanEstimator(
        table_statistics,
        table_columns=TABLE_COLUMNS,
    )

    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    queries = workload["queries"]

    if query_id is not None:
        queries = [query for query in queries if query["id"] == query_id]

        if not queries:
            raise ValueError(f"Unknown workload query: {query_id}")

    records: list[dict[str, Any]] = []

    for query in queries:
        plans = compile_optimized_sql(
            query["sql"],
            compiler,
            table_statistics,
            table_columns=TABLE_COLUMNS,
            frames=FRAMES,
            enable_join_ordering=False,
            enable_logical_rewrites=False,
        )

        if len(plans) != 1:
            raise ValueError(
                f"{query['id']}: expected one logical plan, got {len(plans)}"
            )

        annotated_plan = estimator.annotate(plans[0])

        query_records = []

        for path, node in iter_nodes(annotated_plan):
            estimated = node["est_rows"]

            actual = measure_node(
                node,
                db_dir=db_dir,
                table_statistics=table_statistics,
            )

            record = {
                "query": query["id"],
                "category": query["category"],
                "node_path": path,
                "operator": node["op"],
                "estimated_rows": estimated,
                "actual_rows": actual,
                "q_error": round(q_error(estimated, actual), 6),
            }

            records.append(record)
            query_records.append(record)

        errors = [record["q_error"] for record in query_records]

        print(
            f"{query['id']}: "
            f"nodes={len(query_records)} "
            f"median_q_error={summary_statistics.median(errors):.3f} "
            f"worst_q_error={max(errors):.3f}"
        )

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

        errors = [record["q_error"] for record in records]

        print("\nCardinality measurement summary")
        print(f"Queries: {len(queries)}")
        print(f"Nodes measured: {len(records)}")
        print(f"Median q-error: {summary_statistics.median(errors):.3f}")
        print(f"Worst q-error: {max(errors):.3f}")
        print(f"Results saved to {output}")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure Module 4 cardinality-estimation accuracy."
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=DB_DIR,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
    )

    args = parser.parse_args()

    measure_workload(
        db_dir=args.db,
        output=args.output,
        query_id=args.query,
    )


if __name__ == "__main__":
    main()
