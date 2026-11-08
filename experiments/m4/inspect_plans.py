"""Inspect optimized and baseline physical plans for Module 4 queries."""

import argparse
import json
from pathlib import Path

from experiments.m4.run_benchmarks import compile_plan
from experiments.m4.validate_workload import (
    DB_DIR,
    WORKLOAD,
    load_statistics,
)
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.storage.catalog import Catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Module 4 physical plans.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_DIR,
    )
    parser.add_argument(
        "--query",
        default="Q14",
    )

    args = parser.parse_args()

    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    matches = [query for query in workload["queries"] if query["id"] == args.query]

    if not matches:
        raise ValueError(f"Unknown query: {args.query}")

    compiler = SQLCompiler(SchemaCatalog(Catalog(args.db)))
    statistics = load_statistics(db_dir=args.db)

    sql = matches[0]["sql"]

    print(f"\nQuery: {args.query}")
    print(f"SQL: {sql}")

    for optimized in (False, True):
        label = "OPTIMIZED" if optimized else "BASELINE"

        plan = compile_plan(
            sql,
            compiler,
            statistics,
            optimized=optimized,
        )

        print(f"\n--- {label} PHYSICAL PLAN ---")
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
