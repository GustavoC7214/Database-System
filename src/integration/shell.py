"""Interactive SQL shell."""

import argparse
import re
import shlex
import sys

from src.integration.engine import DatabaseEngine
from src.sql.parser import parse_sql


def format_result(result) -> None:
    if result.columns is not None:
        print(" | ".join(result.columns))
        for row in result.rows or []:
            print(" | ".join(str(value) for value in row))

    print(result.message)

    if result.estimated_io is not None:
        print(f"Estimated I/O: {result.estimated_io}")

    if result.actual_io is not None and result.estimated_io is not None:
        print(f"Actual I/O: {result.actual_io}")
        print(f"Execution counters: {result.counters}")


def run_command(engine: DatabaseEngine, source: str) -> None:
    command = source.strip().rstrip(";").strip()

    match = re.fullmatch(r"SET\s+frames\s*=\s*(\d+)", command, re.IGNORECASE)
    if match:
        engine.set_frames(int(match.group(1)))
        print(f"Buffer frames: {engine.frames}")
        return

    match = re.fullmatch(
        r"ANALYZE\s+([A-Za-z_][A-Za-z_0-9]*)",
        command,
        re.IGNORECASE,
    )
    if match:
        format_result(engine.analyze(match.group(1)))
        return

    if command.upper().startswith("LOAD "):
        parts = shlex.split(command)
        if len(parts) != 4 or parts[2].upper() != "FROM":
            raise ValueError("Expected LOAD table FROM 'filename'")
        format_result(engine.load(parts[1], parts[3]))
        return

    match = re.match(
        r"EXPLAIN(\s+ANALYZE)?\s+(.+)",
        command,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        statements = parse_sql(match.group(2))
        if len(statements) != 1:
            raise ValueError("EXPLAIN requires exactly one query")
        format_result(
            engine.query(
                statements[0],
                explain=True,
                execute=bool(match.group(1)),
            )
        )
        return

    for result in engine.execute_sql(source):
        format_result(result)


def split_complete_statements(source: str) -> tuple[list[str], str]:
    """Extract complete semicolon-terminated statements.

    Semicolons inside single-quoted SQL strings do not terminate statements.
    SQL escapes an apostrophe by doubling it.
    """
    statements = []
    start = 0
    index = 0
    in_string = False

    while index < len(source):
        character = source[index]

        if character == "'":
            if in_string and index + 1 < len(source) and source[index + 1] == "'":
                index += 2
                continue

            in_string = not in_string

        elif character == ";" and not in_string:
            statements.append(source[start : index + 1])
            start = index + 1

        index += 1

    return statements, source[start:]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Database SQL shell")
    parser.add_argument("--db", required=True)
    parser.add_argument("--frames", type=int, default=32)
    args = parser.parse_args(argv)

    try:
        engine = DatabaseEngine(args.db, args.frames)
    except ValueError as exc:
        parser.error(str(exc))

    print("Database SQL shell. Type .quit to exit.")
    buffer = ""

    while True:
        try:
            line = input("db> " if not buffer else "... ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            buffer = ""
            continue

        if not buffer and line.strip().lower() in {".quit", ".exit"}:
            break

        buffer += line + "\n"
        statements, buffer = split_complete_statements(buffer)

        for statement in statements:
            try:
                run_command(engine, statement)
            except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
                print(f"Error: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
