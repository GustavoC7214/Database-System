from src.execution.temp_run import read_tuples, tuple_size, write_tuple


def test_temp_run_round_trip(tmp_path):
    path = tmp_path / "run.tmp"

    rows = [
        (1, "Alice"),
        (2, "Bob"),
        (3, "Café"),
        (4, 12.5),
    ]

    with path.open("wb") as file:
        for row in rows:
            assert write_tuple(file, row) == tuple_size(row)

    assert list(read_tuples(path)) == rows
    assert path.stat().st_size == sum(tuple_size(row) for row in rows)
