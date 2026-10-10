import argparse
import sys
from pathlib import Path

from src.engine.database import Database
from src.engine.query_processor import QueryProcessor
from src.engine.relation import Relation
from src.lexer.tokenizer import LexicalError, Tokenizer
from src.parser.parser import ParseError, Parser
from src.parser.tree_printer import print_tree


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Relational Algebra Query Processor"
    )

    parser.add_argument(
        "query",
        help="Relational algebra query to parse or execute",
    )

    parser.add_argument(
        "--file",
        type=Path,
        help="File containing relation definitions",
    )

    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print the parse tree without executing the query",
    )

    return parser.parse_args()


def load_relations(
    file_path: Path,
    processor: QueryProcessor,
) -> None:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Relation file not found: {file_path}"
        )

    if not file_path.is_file():
        raise IsADirectoryError(
            f"Relation path is not a file: {file_path}"
        )

    source = file_path.read_text(encoding="utf-8")

    definition_lines = []

    for line in source.splitlines():
        stripped_line = line.strip()

        if not stripped_line or stripped_line.startswith("//"):
            continue

        definition_lines.append(line)

        if stripped_line.startswith("}"):
            definition = "\n".join(definition_lines)
            processor.execute(definition)
            definition_lines = []

    if definition_lines:
        processor.execute("\n".join(definition_lines))


def format_table(relation: Relation) -> str:
    relation_names = {
        attribute.relation
        for attribute in relation.attributes
    }

    qualify_headers = len(relation_names) > 1

    headers = [
        (
            f"{attribute.relation}.{attribute.name}"
            if qualify_headers
            else attribute.name
        )
        for attribute in relation.attributes
    ]

    rows = [
        [str(value) for value in row.values]
        for row in relation.rows
    ]

    widths = []

    for column_index, header in enumerate(headers):
        width = len(header)

        for row in rows:
            width = max(
                width,
                len(row[column_index]),
            )

        widths.append(width)

    header_line = " | ".join(
        header.ljust(width)
        for header, width in zip(headers, widths)
    )

    separator_line = "-+-".join(
        "-" * width
        for width in widths
    )

    lines = [
        header_line,
        separator_line,
    ]

    if not rows:
        lines.append("(no rows)")
    else:
        for row in rows:
            lines.append(
                " | ".join(
                    value.ljust(width)
                    for value, width in zip(row, widths)
                )
            )

    return "\n".join(lines)


def print_query_tree(source: str) -> None:
    tokens = Tokenizer(source).tokenize()
    ast = Parser(tokens).parse()

    print(print_tree(ast))


def execute_query(
    source: str,
    file_path: Path,
) -> None:
    database = Database()
    processor = QueryProcessor(database)

    load_relations(file_path, processor)

    result = processor.execute(source)

    print(format_table(result))


def error_category(error: Exception) -> str:
    if isinstance(error, LexicalError):
        return "Lexical Error"

    if isinstance(error, ParseError):
        return "Syntax Error"

    if isinstance(error, (NameError, KeyError)):
        return "Name Error"

    if isinstance(error, TypeError):
        return "Type Error"

    if isinstance(error, ValueError):
        return "Schema Error"

    if isinstance(error, (FileNotFoundError, OSError)):
        return "File Error"

    return "Error"


def main() -> int:
    args = parse_arguments()

    try:
        if args.tree:
            print_query_tree(args.query)
            return 0

        if args.file is None:
            print(
                "Usage Error: --file is required when executing a query.",
                file=sys.stderr,
            )
            return 1

        execute_query(
            args.query,
            args.file,
        )

        return 0

    except (
        LexicalError,
        ParseError,
        NameError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
    ) as error:
        category = error_category(error)

        print(
            f"{category}: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())