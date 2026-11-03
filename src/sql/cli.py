"""Command-line interface for the Module 3 SQL front end."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.sql import ast
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.sql.parser import parse_sql
from src.sql.semantic import NameResolver


def build_parser() -> argparse.ArgumentParser:
    """Build the SQL command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="sql",
        description="SQL parser, semantic checker, and logical compiler",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    parse = commands.add_parser(
        "parse",
        help="Parse SQL and optionally display its AST",
    )
    parse_source = parse.add_mutually_exclusive_group(required=True)
    parse_source.add_argument("--query", help="SQL query text")
    parse_source.add_argument("--file", help="SQL source file")
    parse.add_argument(
        "--explain",
        action="store_true",
        help="Display the parsed AST as JSON",
    )

    check = commands.add_parser(
        "check",
        help="Validate SQL against a database catalog",
    )
    check.add_argument(
        "--db",
        required=True,
        help="Existing database directory",
    )
    check_source = check.add_mutually_exclusive_group(required=True)
    check_source.add_argument("--query", help="SQL query text")
    check_source.add_argument("--file", help="SQL source file")

    compile_command = commands.add_parser(
        "compile",
        help="Compile SQL into logical operator trees",
    )
    compile_command.add_argument(
        "--db",
        required=True,
        help="Existing database directory",
    )
    compile_source = compile_command.add_mutually_exclusive_group(required=True)
    compile_source.add_argument("--query", help="SQL query text")
    compile_source.add_argument("--file", help="SQL source file")
    compile_command.add_argument(
        "--json",
        action="store_true",
        help="Display logical plans as formatted JSON",
    )

    return parser


def _read_source(args: argparse.Namespace) -> str:
    """Read SQL from either --query or --file."""
    if args.query is not None:
        return args.query

    return Path(args.file).read_text(encoding="utf-8")


def _queries(source: str) -> tuple[ast.Query, ...]:
    """Parse SQL and require query statements for check/compile."""
    statements = parse_sql(source)

    for statement in statements:
        if not isinstance(statement, (ast.Select, ast.SetOperation)):
            raise TypeError(
                "SQL check and compile currently support SELECT "
                "queries only; CREATE TABLE and INSERT are not "
                "supported by these commands."
            )

    return statements


def _parse_command(source: str, explain: bool) -> None:
    statements = parse_sql(source)

    if explain:
        print(
            json.dumps(
                [asdict(statement) for statement in statements],
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"OK: {len(statements)} SQL statements parsed.")


def _check_command(source: str, catalog: SchemaCatalog) -> None:
    queries = _queries(source)
    resolver = NameResolver(catalog)

    for query in queries:
        resolver.analyze(query)

    print(f"OK: {len(queries)} SQL statements validated.")


def _compile_command(
    source: str,
    catalog: SchemaCatalog,
    json_output: bool,
) -> None:
    queries = _queries(source)
    compiler = SQLCompiler(catalog)
    plans = [compiler.compile(query) for query in queries]

    if json_output:
        print(json.dumps(plans, indent=2, ensure_ascii=False))
        return

    for index, plan in enumerate(plans, start=1):
        print(f"Logical plan {index}:")
        print(json.dumps(plan, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    """Run a SQL CLI command and return its process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_source(args)

        if args.command == "parse":
            _parse_command(source, args.explain)
            return 0

        db_path = Path(args.db)

        if not db_path.is_dir():
            print(
                f"error: input: Database directory does not exist: {db_path}",
                file=sys.stderr,
            )
            return 2

        if not (db_path / "catalog.db").is_file():
            print(
                f"error: input: Database catalog does not exist: "
                f"{db_path / 'catalog.db'}",
                file=sys.stderr,
            )
            return 2

        catalog = SchemaCatalog.from_directory(args.db)

        if args.command == "check":
            _check_command(source, catalog)
            return 0

        if args.command == "compile":
            _compile_command(source, catalog, args.json)
            return 0

    except (OSError, UnicodeError) as exc:
        print(f"error: input: {exc}", file=sys.stderr)
        return 2

    except (ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
