from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_generator import (
    calculate_key_count,
    generate_r,
    generate_s,
)


def count_matches(
    r_rows: list[tuple[int, int]],
    s_rows: list[tuple[int, int]],
) -> list[int]:
    matches = []

    for _, r_b in r_rows:
        match_count = 0

        for s_b, _ in s_rows:
            if r_b == s_b:
                match_count += 1

        matches.append(match_count)

    return matches


def test_generate_r_creates_requested_number_of_rows():
    rows = generate_r(
        n=10,
        key_count=5,
    )

    assert len(rows) == 10


def test_generate_s_creates_requested_number_of_rows():
    rows = generate_s(
        m=20,
        key_count=5,
    )

    assert len(rows) == 20


def test_generated_r_rows_are_unique():
    rows = generate_r(
        n=20,
        key_count=5,
    )

    assert len(rows) == len(set(rows))


def test_generated_s_rows_are_unique():
    rows = generate_s(
        m=20,
        key_count=5,
    )

    assert len(rows) == len(set(rows))


def test_match_rate_one():
    key_count = calculate_key_count(
        m=8,
        match_rate=1,
    )

    r_rows = generate_r(
        n=8,
        key_count=key_count,
    )

    s_rows = generate_s(
        m=8,
        key_count=key_count,
    )

    assert count_matches(r_rows, s_rows) == [1] * 8


def test_match_rate_two():
    key_count = calculate_key_count(
        m=8,
        match_rate=2,
    )

    r_rows = generate_r(
        n=8,
        key_count=key_count,
    )

    s_rows = generate_s(
        m=8,
        key_count=key_count,
    )

    assert count_matches(r_rows, s_rows) == [2] * 8


def test_match_rate_four():
    key_count = calculate_key_count(
        m=8,
        match_rate=4,
    )

    r_rows = generate_r(
        n=8,
        key_count=key_count,
    )

    s_rows = generate_s(
        m=8,
        key_count=key_count,
    )

    assert count_matches(r_rows, s_rows) == [4] * 8


def test_match_rate_eight():
    key_count = calculate_key_count(
        m=8,
        match_rate=8,
    )

    r_rows = generate_r(
        n=8,
        key_count=key_count,
    )

    s_rows = generate_s(
        m=8,
        key_count=key_count,
    )

    assert count_matches(r_rows, s_rows) == [8] * 8