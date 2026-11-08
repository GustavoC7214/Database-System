"""Run reproducible SQL workloads and export query metrics to CSV."""

import argparse
import csv
import sys
from pathlib import Path
from time import perf_counter

from src.integration.engine import DatabaseEngine
from src.sql import ast
from src.sql.parser import parse_sql

FIELDNAMES = [
    "query_id",
    "status",
    "result_rows",
    "page_reads",
    "page_writes",
    "total_page_io",
    "estimated_page_io",
    "physical_execution_ms",
    "end_to_end_ms",
    "estimated_root_rows",
    "actual_root_rows",
    "root_q_error",
    "error",
]


def split_statements(source: str) -> list[str]:
    """Split SQL on semicolons outside strings and comments."""
    statements = []
    current = []
    i = 0
    quote = False
    line_comment = False
    block_comment = False

    while i < len(source):
        char = source[i]
        next_char = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
                current.append(" ")
            i += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                current.append(" ")
                i += 2
            else:
                i += 1
            continue

        if quote:
            current.append(char)
            if char == "'" and next_char == "'":
                current.append(next_char)
                i += 2
                continue
            if char == "'":
                quote = False
            i += 1
            continue

        if char == "'":
            quote = True
            current.append(char)
        elif char == "-" and next_char == "-":
            line_comment = True
        elif char == "/" and next_char == "*":
            block_comment = True
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement + ";")
            current = []
        else:
            current.append(char)

        i += 1

    if quote:
        raise ValueError("Unterminated SQL string")
    if block_comment:
        raise ValueError("Unterminated SQL block comment")

    remaining = "".join(current).strip()
    if remaining:
        raise ValueError(
            "SQL workload ends with an incomplete statement (missing semicolon)"
        )

    return statements


def root_q_error(estimated: int, actual: int) -> float:
    """Symmetric cardinality error; use 1 as a zero-count floor."""
    estimate = max(1, estimated)
    observed = max(1, actual)
    return max(estimate / observed, observed / estimate)


def run_workload(
    engine: DatabaseEngine,
    statements: list[str],
) -> list[dict]:
    """Execute SELECT queries independently and collect metrics."""
    records = []

    for index, source in enumerate(statements, start=1):
        record = dict.fromkeys(FIELDNAMES, "")
        record["query_id"] = f"Q{index:02d}"
        record["status"] = "error"

        started = perf_counter()

        try:
            parsed = parse_sql(source)

            if len(parsed) != 1:
                raise ValueError("Expected exactly one SQL statement")

            statement = parsed[0]

            if not isinstance(statement, (ast.Select, ast.SetOperation)):
                raise TypeError("Benchmark statements must be SELECT queries")

            result = engine.query(
                statement,
                explain=True,
                execute=True,
            )

            counters = result.counters or {}
            actual_rows = (
                result.actual_rows
                if result.actual_rows is not None
                else len(result.rows or [])
            )

            record.update(
                status="ok",
                result_rows=len(result.rows or []),
                page_reads=counters.get("page_reads", 0),
                page_writes=counters.get("page_writes", 0),
                total_page_io=result.actual_io,
                estimated_page_io=result.estimated_io,
                physical_execution_ms=(
                    f"{result.execution_time_ms:.3f}"
                    if result.execution_time_ms is not None
                    else ""
                ),
                estimated_root_rows=result.estimated_rows,
                actual_root_rows=actual_rows,
            )

            if result.estimated_rows is not None:
                record["root_q_error"] = (
                    f"{root_q_error(result.estimated_rows, actual_rows):.3f}"
                )

        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
            OSError,
            RuntimeError,
        ) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"

        record["end_to_end_ms"] = f"{(perf_counter() - started) * 1000.0:.3f}"

        records.append(record)

    return records


def write_csv(records: list[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark SQL queries against the integrated database."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=32)
    parser.add_argument(
        "--setup",
        type=Path,
        help="Optional SQL setup script, executed before benchmarking.",
    )
    args = parser.parse_args(argv)

    if args.frames < 4:
        parser.error("--frames must be at least 4")

    try:
        engine = DatabaseEngine(args.db, frames=args.frames)

        if args.setup is not None:
            setup_sql = args.setup.read_text(encoding="utf-8")
            for statement in split_statements(setup_sql):
                engine.execute_sql(statement)

        workload_sql = args.workload.read_text(encoding="utf-8")
        statements = split_statements(workload_sql)

        if not statements:
            raise ValueError("Workload contains no SQL statements")

        records = run_workload(engine, statements)
        write_csv(records, args.output)

    except (OSError, ValueError, TypeError) as exc:
        print(f"Benchmark setup failed: {exc}", file=sys.stderr)
        return 2

    successful = sum(record["status"] == "ok" for record in records)
    failed = len(records) - successful

    print(f"Queries: {len(records)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Results: {args.output}")

    for record in records:
        if record["status"] == "error":
            print(
                f"{record['query_id']}: {record['error']}",
                file=sys.stderr,
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
