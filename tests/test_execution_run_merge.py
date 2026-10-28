import pytest

from src.execution.page_manager import SharedPageManager
from src.execution.run_merge import merge_runs, merge_to_temp_run
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter


def create_run(path, rows):
    with TempPageWriter(path) as writer:
        for row in rows:
            writer.write(row)


def test_merge_runs_preserves_duplicates(tmp_path):
    run1 = tmp_path / "run1.tmp"
    run2 = tmp_path / "run2.tmp"
    run3 = tmp_path / "run3.tmp"

    create_run(run1, [(1,), (4,), (7,)])
    create_run(run2, [(2,), (4,), (8,)])
    create_run(run3, [(3,), (5,), (9,)])

    result = list(
        merge_runs(
            [run1, run2, run3],
            sort_key=lambda row: row[0],
        )
    )

    assert result == [
        (1,),
        (2,),
        (3,),
        (4,),
        (4,),
        (5,),
        (7,),
        (8,),
        (9,),
    ]


def test_merge_to_temp_run(tmp_path):
    run1 = tmp_path / "run1.tmp"
    run2 = tmp_path / "run2.tmp"

    create_run(run1, [(1,), (3,), (5,)])
    create_run(run2, [(2,), (3,), (4,)])

    merged_path = merge_to_temp_run(
        [run1, run2],
        sort_key=lambda row: row[0],
        temp_dir=tmp_path,
    )

    try:
        with TempPageReader(merged_path) as reader:
            result = []

            while (row := reader.read()) is not None:
                result.append(row)

        assert result == [
            (1,),
            (2,),
            (3,),
            (3,),
            (4,),
            (5,),
        ]
    finally:
        merged_path.unlink(missing_ok=True)


def test_merge_runs_with_empty_input(tmp_path):
    assert list(merge_runs([], sort_key=lambda row: row[0])) == []


def test_merge_runs_descending(tmp_path):
    run1 = tmp_path / "run1.tmp"
    run2 = tmp_path / "run2.tmp"

    create_run(run1, [(9,), (5,), (1,)])
    create_run(run2, [(8,), (6,), (2,)])

    result = list(
        merge_runs(
            [run1, run2],
            sort_key=lambda row: -row[0] if isinstance(row[0], (int, float)) else 0,
        )
    )

    assert result == [
        (9,),
        (8,),
        (6,),
        (5,),
        (2,),
        (1,),
    ]


def test_merge_runs_with_shared_frames(tmp_path):
    pages = SharedPageManager(frames=4)

    paths = [
        tmp_path / "run1.tmp",
        tmp_path / "run2.tmp",
        tmp_path / "run3.tmp",
    ]

    create_run(paths[0], [(1,), (4,), (7,)])
    create_run(paths[1], [(2,), (5,), (8,)])
    create_run(paths[2], [(3,), (6,), (9,)])

    reads = []

    result = list(
        merge_runs(
            paths,
            sort_key=lambda row: row[0],
            on_page_read=reads.append,
            pages=pages,
        )
    )

    assert result == [(i,) for i in range(1, 10)]
    assert sum(reads) == 3
    assert pages.reserved_frames == set()


def test_merge_to_temp_run_with_shared_frames(tmp_path):
    pages = SharedPageManager(frames=4)

    paths = [
        tmp_path / "run1.tmp",
        tmp_path / "run2.tmp",
        tmp_path / "run3.tmp",
    ]

    create_run(paths[0], [(1,), (4,), (7,)])
    create_run(paths[1], [(2,), (5,), (8,)])
    create_run(paths[2], [(3,), (6,), (9,)])

    reads = []
    writes = []

    merged_path = merge_to_temp_run(
        paths,
        sort_key=lambda row: row[0],
        temp_dir=tmp_path,
        on_page_read=reads.append,
        on_page_write=writes.append,
        pages=pages,
    )

    try:
        with TempPageReader(merged_path) as reader:
            result = []

            while (row := reader.read()) is not None:
                result.append(row)

        assert result == [(i,) for i in range(1, 10)]
        assert sum(reads) == 3
        assert sum(writes) == 1
        assert pages.reserved_frames == set()
    finally:
        merged_path.unlink(missing_ok=True)


def test_merge_rejects_insufficient_shared_frames(tmp_path):
    pages = SharedPageManager(frames=4)

    paths = [
        tmp_path / "run1.tmp",
        tmp_path / "run2.tmp",
        tmp_path / "run3.tmp",
    ]

    create_run(paths[0], [(1,), (4,)])
    create_run(paths[1], [(2,), (5,)])
    create_run(paths[2], [(3,), (6,)])

    with pages.temporary_frames(1):
        with pytest.raises(RuntimeError, match="Insufficient shared frames"):
            merge_to_temp_run(
                paths,
                sort_key=lambda row: row[0],
                temp_dir=tmp_path,
                pages=pages,
            )

        assert len(pages.reserved_frames) == 1

    assert pages.reserved_frames == set()
