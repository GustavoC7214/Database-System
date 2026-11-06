"""Command-line interface for the Module 4 query optimizer."""

import argparse
import json
from dataclasses import asdict

from src.optimizer.analyze import analyze_table


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
    analyze.add_argument("--table", required=True)
    analyze.add_argument("--buckets", type=int, default=20)
    analyze.add_argument("--frames", type=int, default=32)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    raise SystemExit(main())
