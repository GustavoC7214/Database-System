"""Command-line interface for the Module 3 SQL front end."""

import argparse
import json
import sys
from dataclasses import fields, is_dataclass
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
        help="Display the parsed AST as an indented tree",
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
                "error: syntax: check and compile currently support "
                "SELECT queries only at line 1, column 1"
            )

    return statements


def _print_ast_tree(value: object, indent: int = 0) -> None:
    """Print an indented representation of the parsed SQL AST."""
    prefix = "  " * indent

    if isinstance(value, (tuple, list)):
        for item in value:
            _print_ast_tree(item, indent)
        return

    if is_dataclass(value) and not isinstance(value, type):
        print(f"{prefix}{type(value).__name__}")

        for field_info in fields(value):
            field_value = getattr(value, field_info.name)

            if isinstance(field_value, (tuple, list)):
                if field_value:
                    print(f"{prefix}  {field_info.name}:")
                    _print_ast_tree(field_value, indent + 2)
            elif is_dataclass(field_value) and not isinstance(field_value, type):
                print(f"{prefix}  {field_info.name}:")
                _print_ast_tree(field_value, indent + 2)
            elif field_value is not None:
                print(f"{prefix}  {field_info.name}: {field_value}")

        return

    print(f"{prefix}{value}")


def _parse_command(source: str, explain: bool) -> None:
    """Parse SQL and optionally print an indented syntax tree."""
    statements = parse_sql(source)

    if explain:
        for index, statement in enumerate(statements, start=1):
            print(f"Statement {index}:")
            _print_ast_tree(statement, 1)
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
                "error: schema: "
                f"Database directory does not exist: {db_path} "
                "at line 1, column 1",
                file=sys.stderr,
            )
            return 1

        if not (db_path / "catalog.db").is_file():
            print(
                "error: schema: "
                f"Database catalog does not exist: {db_path / 'catalog.db'} "
                "at line 1, column 1",
                file=sys.stderr,
            )
            return 1

        catalog = SchemaCatalog.from_directory(args.db)

        if args.command == "check":
            _check_command(source, catalog)
            return 0

        if args.command == "compile":
            _compile_command(source, catalog, args.json)
            return 0

    except (OSError, UnicodeError) as exc:
        print(
            f"error: schema: {exc} at line 1, column 1",
            file=sys.stderr,
        )
        return 1

    except (ValueError, TypeError) as exc:
        message = str(exc)

        if not message.startswith("error: "):
            message = f"error: schema: {message} at line 1, column 1"

        print(message, file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
