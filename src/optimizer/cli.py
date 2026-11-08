"""Command-line interface for the Module 4 query optimizer."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.optimizer.analyze import analyze_table
from src.optimizer.join_order import (
    JoinEdge,
    format_dp_table,
    optimize_join_order,
)
from src.optimizer.physical_lowering import (
    UnsupportedPhysicalPlan,
    lower_physical_plan,
)
from src.optimizer.pipeline import optimize_logical_plan
from src.optimizer.plan_cost import CostedPlan, PhysicalCostEstimator
from src.optimizer.sql_join_order import (
    _extract_join_tree,
    optimize_sql_join_order,
)
from src.optimizer.sql_pipeline import compile_optimized_sql
from src.optimizer.statistics import StatisticsStore, TableStatistics
from src.optimizer.statistics_fallback import complete_statistics
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opt",
        description="Database query optimizer",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    analyze = commands.add_parser(
        "analyze",
        help="Collect and persist table statistics",
    )
    analyze.add_argument("--db", required=True)
    analyze.add_argument("--table", required=False)
    analyze.add_argument("--buckets", type=int, default=20)
    analyze.add_argument("--frames", type=int, default=32)

    plan = commands.add_parser(
        "plan",
        help="Compile SQL and output a logical query plan",
    )
    plan.add_argument("--db", required=True)
    plan_input = plan.add_mutually_exclusive_group(required=True)
    plan_input.add_argument("--sql")
    plan_input.add_argument("--logical", help="Input logical-plan JSON file")
    plan.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output",
    )
    plan.add_argument("--frames", type=int, default=32)
    plan.add_argument(
        "--rewrites",
        action="store_true",
        help="Enable logical predicate and projection rewrites",
    )
    plan.add_argument(
        "--no-join-order",
        action="store_true",
        help="Disable dynamic-programming join ordering",
    )
    plan.add_argument(
        "--physical",
        action="store_true",
        help="Export Module 2 executable physical-plan JSON",
    )
    explain = commands.add_parser(
        "explain",
        help="Display estimated rows, pages, algorithms, and I/O",
    )
    explain.add_argument("--db", required=True)
    explain_input = explain.add_mutually_exclusive_group(required=True)
    explain_input.add_argument("--sql")
    explain_input.add_argument("--logical", help="Input logical-plan JSON file")
    explain.add_argument("--frames", type=int, default=32)
    explain.add_argument(
        "--rewrites",
        action="store_true",
        help="Enable logical predicate and projection rewrites",
    )
    explain.add_argument(
        "--no-join-order",
        action="store_true",
        help="Disable dynamic-programming join ordering",
    )
    dp_table = commands.add_parser(
        "dp-table",
        help="Display the dynamic-programming join-order table",
    )
    dp_table.add_argument("--db", required=True)
    dp_table.add_argument(
        "--tables",
        nargs="+",
        required=False,
        help="Base tables to include in join-order optimization",
    )
    dp_table.add_argument(
        "--join",
        action="append",
        required=False,
        help="Equality join, e.g. Emp.did=Dept.did; repeat for each edge",
    )
    dp_table.add_argument("--frames", type=int, default=32)

    dp_table.add_argument(
        "--logical",
        help="Extract the join-order problem from logical-plan JSON",
    )

    return parser


def _scan_tables(node: dict[str, Any]) -> set[str]:
    """Collect base-table references from a logical plan."""
    tables: set[str] = set()

    if node.get("op") == "scan":
        tables.add(node["table"])

    for key in ("child", "left", "right"):
        child = node.get(key)

        if isinstance(child, dict):
            tables.update(_scan_tables(child))

    return tables


def _has_join(node: dict[str, Any]) -> bool:
    """Check whether a logical plan contains an explicit join."""
    if node.get("op") == "join":
        return True

    return any(
        _has_join(node[key])
        for key in ("child", "left", "right")
        if isinstance(node.get(key), dict)
    )


def _load_query_metadata(
    db_dir: str,
    plans: list[dict[str, Any]],
    catalog: SchemaCatalog,
    *,
    require_join_statistics: bool,
) -> tuple[
    dict[str, TableStatistics],
    dict[str, list[str]],
]:
    """Load only the metadata needed by the compiled queries."""
    tables = sorted(
        set().union(*(_scan_tables(plan) for plan in plans)) if plans else set()
    )

    store = StatisticsStore(db_dir)
    statistics: dict[str, TableStatistics] = {}
    table_columns: dict[str, list[str]] = {}
    missing: list[str] = []

    for table in tables:
        schema = catalog.get_table(table)

        table_columns[table] = [column.name for column in schema.columns]

        stored = store.load(table)

        if stored is None:
            missing.append(table)
        else:
            statistics[table] = stored

    statistics = complete_statistics(set(tables), statistics)

    return statistics, table_columns


def _plan_command(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Compile and optionally optimize SQL using persisted metadata."""
    catalog = SchemaCatalog.from_directory(args.db)
    compiler = SQLCompiler(catalog)

    original = compiler.compile_sql(args.sql)

    if not original:
        raise ValueError("SQL input contains no SELECT queries")

    ordering = not args.no_join_order

    statistics, table_columns = _load_query_metadata(
        args.db,
        original,
        catalog,
        require_join_statistics=(
            ordering and any(_has_join(plan) for plan in original)
        ),
    )

    return compile_optimized_sql(
        args.sql,
        compiler,
        statistics,
        table_columns=table_columns,
        frames=args.frames,
        enable_join_ordering=ordering,
        enable_logical_rewrites=args.rewrites,
    )


def _format_cost_tree(
    node: CostedPlan,
    depth: int = 0,
) -> list[str]:
    """Format a recursive estimated I/O tree."""
    indentation = "  " * depth

    line = (
        f"{indentation}{node.operation.upper()} "
        f"[{node.algorithm}] "
        f"rows={node.rows} "
        f"pages={node.pages} "
        f"local_io={node.local_io} "
        f"total_io={node.total_io}"
    )

    lines = [line]

    for child in node.children:
        lines.extend(_format_cost_tree(child, depth + 1))

    return lines


def _explain_command(args: argparse.Namespace) -> str:
    """Compile SQL and format estimated logical/physical costs."""
    plans = _plan_command(args)

    catalog = SchemaCatalog.from_directory(args.db)

    statistics, table_columns = _load_query_metadata(
        args.db,
        plans,
        catalog,
        require_join_statistics=False,
    )

    referenced_tables = sorted(set().union(*(_scan_tables(plan) for plan in plans)))

    missing = [table for table in referenced_tables if table not in statistics]

    if missing:
        names = ", ".join(missing)
        raise ValueError(f"EXPLAIN requires ANALYZE statistics for: {names}")

    estimator = PhysicalCostEstimator(
        statistics,
        frames=args.frames,
        table_columns=table_columns,
    )

    output = [
        "OPTIMIZER EXPLAIN",
        f"Buffer frames: {args.frames}",
        "Costs are estimated page I/O, not measured disk I/O.",
        "Algorithms are cost-model choices, not guaranteed physical lowering.",
    ]

    for index, plan in enumerate(plans, start=1):
        costed = estimator.estimate(plan)

        output.extend(
            [
                "",
                f"Query {index}",
                f"Estimated output rows: {costed.rows}",
                f"Estimated output pages: {costed.pages}",
                f"Estimated total I/O: {costed.total_io}",
                "",
                "Plan:",
                *_format_cost_tree(costed),
            ]
        )

    return "\n".join(output)


def _parse_join_edge(source: str) -> JoinEdge:
    """Parse a qualified equality join for DP optimization."""
    parts = source.split("=")

    if len(parts) != 2:
        raise ValueError(
            f"Invalid join condition: {source}. Expected Table.column=Table.column"
        )

    left, right = (part.strip() for part in parts)

    def parse_column(value: str) -> tuple[str, str]:
        pieces = value.split(".")

        if len(pieces) != 2:
            raise ValueError(f"Invalid qualified column: {value}")

        table, column = pieces

        if not (
            table
            and column
            and table.isascii()
            and column.isascii()
            and table.isidentifier()
            and column.isidentifier()
        ):
            raise ValueError(f"Invalid qualified column: {value}")

        return table, column

    left_table, left_column = parse_column(left)
    right_table, right_column = parse_column(right)

    return JoinEdge(
        left_table=left_table,
        left_column=left_column,
        right_table=right_table,
        right_column=right_column,
    )


def _dp_table_command(args: argparse.Namespace) -> str:
    """Load statistics and display the retained DP join-order table."""
    tables = args.tables

    if len(tables) < 2:
        raise ValueError("DP join ordering requires at least two tables")

    if len(tables) != len(set(tables)):
        raise ValueError("Duplicate tables are not allowed")

    catalog = SchemaCatalog.from_directory(args.db)
    store = StatisticsStore(args.db)

    table_columns: dict[str, set[str]] = {}
    statistics: dict[str, TableStatistics] = {}
    missing: list[str] = []

    for table in tables:
        schema = catalog.get_table(table)
        table_columns[table] = {column.name for column in schema.columns}

        stored = store.load(table)

        if stored is None:
            missing.append(table)
        else:
            statistics[table] = stored

    statistics = complete_statistics(set(tables), statistics)

    edges = [_parse_join_edge(source) for source in args.join]

    for edge in edges:
        for table, column in (
            (edge.left_table, edge.left_column),
            (edge.right_table, edge.right_column),
        ):
            if table not in table_columns:
                raise ValueError(f"Join references table not in --tables: {table}")

            if column not in table_columns[table]:
                raise ValueError(f"Unknown join column: {table}.{column}")

    result = optimize_join_order(
        statistics,
        edges,
        frames=args.frames,
    )

    return format_dp_table(result)


def _read_logical_plan(path: str) -> dict[str, Any]:
    """Read one logical query plan from a JSON file."""
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read logical plan: {exc}") from exc

    try:
        plan = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid logical-plan JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(plan, dict):
        raise TypeError("Logical plan must be a JSON object")

    if not isinstance(plan.get("op"), str):
        raise TypeError("Logical plan must contain a string 'op' field")

    return plan


def _logical_metadata(
    db_dir: str,
    plan: dict[str, Any],
) -> tuple[dict[str, TableStatistics], dict[str, list[str]]]:
    """Load catalog metadata for a logical-plan tree."""
    catalog = SchemaCatalog.from_directory(db_dir)

    return _load_query_metadata(
        db_dir,
        [plan],
        catalog,
        require_join_statistics=False,
    )


def _optimize_logical_input(
    args: argparse.Namespace,
) -> tuple[
    dict[str, Any],
    dict[str, TableStatistics],
    dict[str, list[str]],
]:
    """Optimize a logical JSON plan without recompiling SQL."""
    original = _read_logical_plan(args.logical)

    statistics, table_columns = _logical_metadata(
        args.db,
        original,
    )

    plan = original

    if args.rewrites:
        plan = optimize_logical_plan(
            plan,
            table_columns=table_columns,
        )

    if not args.no_join_order:
        plan = optimize_sql_join_order(
            plan,
            statistics,
            table_columns=table_columns,
            frames=args.frames,
        )

    return plan, statistics, table_columns


def _logical_plan_command(args: argparse.Namespace) -> dict[str, Any]:
    """Return one Module 2 executable physical-plan object."""
    plan, statistics, table_columns = _optimize_logical_input(args)

    return lower_physical_plan(
        plan,
        statistics,
        table_columns=table_columns,
        frames=args.frames,
    )


def _logical_explain_command(args: argparse.Namespace) -> str:
    """Explain the optimized logical-plan input."""
    plan, statistics, table_columns = _optimize_logical_input(args)

    missing = sorted(_scan_tables(plan) - statistics.keys())

    if missing:
        raise ValueError(
            "EXPLAIN requires ANALYZE statistics for: " + ", ".join(missing)
        )

    estimator = PhysicalCostEstimator(
        statistics,
        frames=args.frames,
        table_columns=table_columns,
    )

    costed = estimator.estimate(plan)

    lines = [
        "OPTIMIZER EXPLAIN",
        f"Buffer frames: {args.frames}",
        "Costs are estimated page I/O, not measured disk I/O.",
        "Algorithms are cost-model choices, not guaranteed physical lowering.",
        "",
        f"Estimated output rows: {costed.rows}",
        f"Estimated output pages: {costed.pages}",
        f"Estimated total I/O: {costed.total_io}",
        "",
        "Plan:",
        *_format_cost_tree(costed),
    ]

    return "\n".join(lines)


def _logical_dp_table_command(args: argparse.Namespace) -> str:
    """Extract a pure equijoin tree and display its DP table."""
    plan = _read_logical_plan(args.logical)

    statistics, table_columns = _logical_metadata(
        args.db,
        plan,
    )

    # Projections and filters can surround a join tree.
    # This first implementation accepts a pure join subtree.
    while plan.get("op") in {"project", "select", "limit"}:
        child = plan.get("child")

        if not isinstance(child, dict):
            raise TypeError("Malformed logical-plan child")

        plan = child

    extracted = _extract_join_tree(plan, table_columns)

    if extracted is None:
        raise ValueError(
            "DP table requires an unaliased inner-equijoin tree "
            "containing only scan and join nodes"
        )

    tables, edges = extracted

    if not 2 <= len(tables) <= 6:
        raise ValueError("DP join ordering requires 2 to 6 tables")

    statistics = complete_statistics(tables, statistics)

    result = optimize_join_order(
        {table: statistics[table] for table in sorted(tables)},
        edges,
        frames=args.frames,
    )

    return format_dp_table(result)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"plan", "explain"} and args.logical is not None:
        if args.frames < 4:
            parser.error("--logical requires at least 4 buffer frames")

        try:
            if args.command == "plan":
                physical = _logical_plan_command(args)
                print(
                    json.dumps(
                        physical,
                        indent=2,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(_logical_explain_command(args))
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            parser.error(str(exc))

        return 0

    if args.command == "dp-table" and args.logical is not None:
        if args.tables or args.join:
            parser.error("--logical cannot be combined with --tables or --join")

        if args.frames < 3:
            parser.error("--frames must be at least 3")

        try:
            print(_logical_dp_table_command(args))
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            parser.error(str(exc))

        return 0

    if args.command == "dp-table" and (not args.tables or not args.join):
        parser.error("Provide --logical, or both --tables and --join")

    if args.command == "analyze":
        if args.buckets < 1:
            parser.error("--buckets must be at least 1")
        if args.frames < 4:
            parser.error("--frames must be at least 4")

        statistics = analyze_table(
            args.db,
            args.table,
            buckets=args.buckets,
            frames=args.frames,
        )

        print(
            json.dumps(
                asdict(statistics),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "plan":
        if args.frames < 3:
            parser.error("--frames must be at least 3")

        if args.physical and args.frames < 4:
            parser.error("--physical requires at least 4 buffer frames")

        try:
            plans = _plan_command(args)

            if args.physical:
                catalog = SchemaCatalog.from_directory(args.db)

                statistics, table_columns = _load_query_metadata(
                    args.db,
                    plans,
                    catalog,
                    require_join_statistics=False,
                )

                required_tables = sorted(
                    set().union(*(_scan_tables(plan) for plan in plans))
                )

                missing = [
                    table for table in required_tables if table not in statistics
                ]

                # A base-table scan can execute without ANALYZE.
                # Joins require statistics to select algorithms.
                if missing and any(_has_join(plan) for plan in plans):
                    raise ValueError(
                        "Physical join planning requires ANALYZE "
                        "statistics for: " + ", ".join(missing)
                    )

                plans = [
                    lower_physical_plan(
                        plan,
                        statistics,
                        table_columns=table_columns,
                        frames=args.frames,
                    )
                    for plan in plans
                ]

        except (
            ValueError,
            TypeError,
            SyntaxError,
            UnsupportedPhysicalPlan,
        ) as exc:
            parser.error(str(exc))

        print(
            json.dumps(
                plans,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "explain":
        if args.frames < 3:
            parser.error("--frames must be at least 3")

        try:
            output = _explain_command(args)
        except (ValueError, TypeError, SyntaxError) as exc:
            parser.error(str(exc))

        print(output)
        return 0

    if args.command == "dp-table":
        if args.frames < 3:
            parser.error("--frames must be at least 3")

        try:
            output = _dp_table_command(args)
        except (ValueError, TypeError, KeyError) as exc:
            parser.error(str(exc))

        print(output)
        return 0

    parser.error("Unknown optimizer command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
