import argparse
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate relation data for relational algebra performance tests."
    )

    parser.add_argument(
        "--n",
        type=int,
        required=True,
        help="Number of tuples to generate for relation R.",
    )

    parser.add_argument(
        "--m",
        type=int,
        required=True,
        help="Number of tuples to generate for relation S.",
    )

    parser.add_argument(
        "--match-rate",
        type=int,
        required=True,
        help="Approximate number of S tuples matching each R tuple.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("performance_data.ra"),
        help="Output relation file.",
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    if args.n <= 0:
        raise ValueError("n must be greater than 0.")

    if args.m <= 0:
        raise ValueError("m must be greater than 0.")

    if args.match_rate <= 0:
        raise ValueError("match rate must be greater than 0.")


def calculate_key_count(
    m: int,
    match_rate: int,
) -> int:
    return max(1, round(m / match_rate))


def generate_r(
    n: int,
    key_count: int,
) -> list[tuple[int, int]]:
    rows = []

    for i in range(n):
        a = i
        b = i % key_count
        rows.append((a, b))

    return rows


def generate_s(
    m: int,
    key_count: int,
) -> list[tuple[int, int]]:
    rows = []

    for i in range(m):
        b = i % key_count
        c = i
        rows.append((b, c))

    return rows


def write_relation_file(
    output_path: Path,
    r_rows: list[tuple[int, int]],
    s_rows: list[tuple[int, int]],
) -> None:
    with output_path.open("w", encoding="utf-8") as file:
        file.write("R (a, b) = {\n")

        for a, b in r_rows:
            file.write(f"{a}, {b}\n")

        file.write("}\n\n")

        file.write("S (b, c) = {\n")

        for b, c in s_rows:
            file.write(f"{b}, {c}\n")

        file.write("}\n")


def main() -> None:
    args = parse_arguments()
    validate_arguments(args)

    key_count = calculate_key_count(
        args.m,
        args.match_rate,
    )

    r_rows = generate_r(
        args.n,
        key_count,
    )

    s_rows = generate_s(
        args.m,
        key_count,
    )

    write_relation_file(
        args.output,
        r_rows,
        s_rows,
    )

    print(f"Generated {args.n} tuples for R.")
    print(f"Generated {args.m} tuples for S.")
    print(f"Match rate: approximately {args.match_rate}.")
    print(f"Written to: {args.output}")


if __name__ == "__main__":
    main()