import pytest

from src.storage.trace_runner import read_trace, run_trace


def test_read_trace_basic(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    assert read_trace(trace_path) == [1, 2, 3, 1, 4, 2]


def test_read_trace_ignores_blank_lines(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n\n2\n   \n3\n",
        encoding="utf-8",
    )

    assert read_trace(trace_path) == [1, 2, 3]


def test_read_trace_ignores_comments(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "# Example trace\n1\n# Another comment\n2\n",
        encoding="utf-8",
    )

    assert read_trace(trace_path) == [1, 2]


def test_read_trace_allows_page_zero(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("0\n1\n", encoding="utf-8")

    assert read_trace(trace_path) == [0, 1]


def test_read_trace_rejects_invalid_page_id(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\ninvalid\n4\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Trace line 3: invalid page ID",
    ):
        read_trace(trace_path)


def test_read_trace_rejects_negative_page_id(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("1\n-2\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Trace line 2: page ID cannot be negative",
    ):
        read_trace(trace_path)


def test_read_trace_empty_file(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("", encoding="utf-8")

    assert read_trace(trace_path) == []


def test_read_trace_missing_file(tmp_path):
    trace_path = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        read_trace(trace_path)


def test_run_trace_lru_reference(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    stats = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=3,
        policy="lru",
    )

    assert stats == {
        "hits": 1,
        "misses": 5,
        "evictions": 2,
        "reads": 5,
        "writes": 0,
    }


def test_run_trace_clock_reference(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    stats = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=3,
        policy="clock",
    )

    assert stats == {
        "hits": 2,
        "misses": 4,
        "evictions": 1,
        "reads": 4,
        "writes": 0,
    }


def test_run_trace_all_hits_after_first_access(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n1\n1\n1\n",
        encoding="utf-8",
    )

    stats = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=2,
    )

    assert stats == {
        "hits": 3,
        "misses": 1,
        "evictions": 0,
        "reads": 1,
        "writes": 0,
    }


def test_run_trace_empty_trace(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("", encoding="utf-8")

    stats = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=3,
    )

    assert stats == {
        "hits": 0,
        "misses": 0,
        "evictions": 0,
        "reads": 0,
        "writes": 0,
    }


def test_run_trace_rejects_zero_frames(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least one frame"):
        run_trace(
            db_dir=tmp_path,
            trace_path=trace_path,
            frames=0,
        )


@pytest.mark.parametrize("policy", ["lru", "clock"])
def test_run_trace_is_repeatable(tmp_path, policy):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    first = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=3,
        policy=policy,
    )

    second = run_trace(
        db_dir=tmp_path,
        trace_path=trace_path,
        frames=3,
        policy=policy,
    )

    assert first == second
