"""Command-line interface for Module 2 physical-plan execution."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.execution.plan_executor import PhysicalPlanExecutor


def build_parser() -> argparse.ArgumentParser:
    """Build the execution CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="exec",
        description="Module 2 physical-plan execution CLI",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    for command in ("run", "trace"):
        subparser = commands.add_parser(
            command,
            help=(
                "Execute a physical plan"
                if command == "run"
                else "Trace per-operator execution statistics"
            ),
        )
        subparser.add_argument(
            "--db",
            required=True,
            help="Database directory",
        )
        subparser.add_argument(
            "--plan",
            required=True,
            help="Path to a JSON physical plan",
        )
        subparser.add_argument(
            "--frames",
            type=int,
            default=32,
            help="Shared execution memory budget in page frames",
        )

        if command == "run":
            subparser.add_argument(
                "--json",
                action="store_true",
                help="Print execution results as JSON",
            )

    return parser


def _format_schema(schema: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Convert schema entries into JSON-compatible objects."""
    return [{"name": name, "type": column_type} for name, column_type in schema]


def _run_output(result: Any) -> dict[str, Any]:
    """Build the structured result for the run command."""
    return {
        "schema": _format_schema(result.schema),
        "rows": [list(row) for row in result.rows],
        "totals": result.counters,
    }


def _print_trace(result: Any) -> None:
    """Print execution statistics for each operator."""
    for entry in result.operator_stats or []:
        depth = entry["depth"]
        operator = entry["operator"]
        counters = entry["counters"]

        indentation = "  " * depth

        print(f"{indentation}{operator}")
        print(
            f"{indentation}  "
            f"tuples_out={counters['tuples_out']} "
            f"comparisons={counters['comparisons']} "
            f"page_reads={counters['page_reads']} "
            f"page_writes={counters['page_writes']}"
        )

    print()
    print("Execution totals:")
    for key, value in result.counters.items():
        print(f"  {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    """Execute a Module 2 CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.frames < 4:
        parser.error("--frames must be at least 4 for Module 2 execution")

    if not Path(args.plan).is_file():
        parser.error(f"Plan file does not exist: {args.plan}")

    try:
        executor = PhysicalPlanExecutor(
            db_dir=args.db,
            frames=args.frames,
        )
        result = executor.execute_file(args.plan)

    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1

    if args.command == "run":
        if args.json:
            print(json.dumps(_run_output(result), ensure_ascii=False))
        else:
            print("Schema:")
            for name, column_type in result.schema:
                print(f"  {name}: {column_type}")

            print("\nRows:")
            for row in result.rows:
                print(row)

            print(f"\nReturned {len(result.rows)} rows")

            print("\nExecution totals:")
            for key, value in result.counters.items():
                print(f"  {key}: {value}")

    elif args.command == "trace":
        _print_trace(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
