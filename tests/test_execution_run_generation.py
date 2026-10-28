from src.execution.operator import Operator
from src.execution.run_generation import generate_sorted_runs
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_run import tuple_size
from src.storage.disk_manager import PAGE_SIZE


class FakeChild(Operator):
    """Minimal in-memory operator for testing run generation."""

    def __init__(self, rows):
        super().__init__()
        self.rows = iter(rows)

    def open(self) -> None:
        pass

    def next(self) -> tuple[int | str | float, ...] | None:
        return next(self.rows, None)

    def close(self) -> None:
        pass


def test_generates_multiple_sorted_runs(tmp_path):
    # Descending input forces each run to perform real sorting.
    rows = [(value, "x" * 100) for value in range(200, 0, -1)]

    child = FakeChild(rows)

    runs = generate_sorted_runs(
        child=child,
        memory_pages=1,
        sort_key=lambda row: row[0],
        temp_dir=tmp_path,
    )

    try:
        # The input exceeds one 4096-byte page.
        assert len(runs) > 1

        recovered = []

        for path in runs:
            with TempPageReader(path) as reader:
                run_rows = []

                while (row := reader.read()) is not None:
                    run_rows.append(row)

            assert reader.page_reads >= 1
            assert path.stat().st_size == reader.page_reads * PAGE_SIZE

            # Every individual run must be sorted.
            assert run_rows == sorted(run_rows, key=lambda row: row[0])

            # Every run must respect its serialized-data budget.
            assert sum(tuple_size(row) for row in run_rows) <= 4096

            recovered.extend(run_rows)

        # Run generation must neither lose nor duplicate tuples.
        assert sorted(recovered) == sorted(rows)

    finally:
        for path in runs:
            path.unlink(missing_ok=True)


def test_generated_runs_respect_physical_page_limit(tmp_path):
    rows = [(i, "x" * 1000) for i in range(30, 0, -1)]
    child = FakeChild(rows)

    runs = generate_sorted_runs(
        child,
        memory_pages=2,
        sort_key=lambda row: row[0],
        temp_dir=tmp_path,
    )

    assert len(runs) > 1

    for path in runs:
        assert path.stat().st_size <= 2 * PAGE_SIZE
        assert path.stat().st_size % PAGE_SIZE == 0
