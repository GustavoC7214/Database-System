import pytest

from src.execution.page_manager import SharedPageManager
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter
from src.storage.disk_manager import PAGE_SIZE


def test_temp_pages_round_trip(tmp_path):
    path = tmp_path / "records.tmp"

    rows = [(index, f"Student-{index}", "x" * 150) for index in range(100)]

    with TempPageWriter(path) as writer:
        for row in rows:
            writer.write(row)

    # The data must span multiple physical pages.
    assert writer.page_writes > 1

    # Every physical page must be exactly 4096 bytes.
    assert path.stat().st_size == writer.page_writes * PAGE_SIZE

    with TempPageReader(path) as reader:
        recovered = []

        while (row := reader.read()) is not None:
            recovered.append(row)

    assert recovered == rows
    assert reader.page_reads == writer.page_writes


def test_temp_pages_preserve_types_and_unicode(tmp_path):
    path = tmp_path / "unicode.tmp"

    rows = [
        (1, "Café", 12.5),
        (2, "日本語", -3.75),
        (3, "Olá, mundo!", 0.0),
    ]

    with TempPageWriter(path) as writer:
        for row in rows:
            writer.write(row)

    with TempPageReader(path) as reader:
        recovered = []

        while (row := reader.read()) is not None:
            recovered.append(row)

    assert recovered == rows
    assert writer.page_writes == 1
    assert reader.page_reads == 1


def test_temp_pages_empty_run(tmp_path):
    path = tmp_path / "empty.tmp"

    with TempPageWriter(path) as writer:
        pass

    assert writer.page_writes == 0
    assert path.stat().st_size == 0

    with TempPageReader(path) as reader:
        assert reader.read() is None

    assert reader.page_reads == 0


def test_temp_pages_reject_oversized_tuple(tmp_path):
    path = tmp_path / "oversized.tmp"

    with (
        TempPageWriter(path) as writer,
        pytest.raises(ValueError, match="capacity"),
    ):
        writer.write((1, "x" * 5000))

    assert writer.page_writes == 0


def test_temp_reader_uses_shared_frame(tmp_path):
    path = tmp_path / "shared_reader.tmp"
    rows = [(i, "x" * 100) for i in range(100)]

    with TempPageWriter(path) as writer:
        for row in rows:
            writer.write(row)

    pages = SharedPageManager(frames=4)

    with pages.temporary_frames(1) as buffers:
        with TempPageReader(path, buffer=buffers[0]) as reader:
            recovered = []

            while (row := reader.read()) is not None:
                recovered.append(row)

            assert reader.page_reads == writer.page_writes

        assert len(pages.reserved_frames) == 1

    assert recovered == rows
    assert pages.reserved_frames == set()


def test_temp_writer_uses_shared_frame(tmp_path):
    path = tmp_path / "shared_writer.tmp"
    rows = [(i, "x" * 100) for i in range(100)]

    pages = SharedPageManager(frames=4)

    with pages.temporary_frames(1) as buffers:
        with TempPageWriter(path, buffer=buffers[0]) as writer:
            for row in rows:
                writer.write(row)

        assert len(pages.reserved_frames) == 1

    with TempPageReader(path) as reader:
        recovered = []

        while (row := reader.read()) is not None:
            recovered.append(row)

    assert recovered == rows
    assert writer.page_writes > 1
    assert reader.page_reads == writer.page_writes
    assert pages.reserved_frames == set()


def test_shared_reader_reuses_frame_across_multiple_pages(tmp_path):
    path = tmp_path / "reuse.tmp"
    rows = [(i, "value" * 200) for i in range(50)]
    with TempPageWriter(path) as writer:
        for row in rows:
            writer.write(row)
    assert writer.page_writes > 2

    pages = SharedPageManager(frames=4)
    with (
        pages.temporary_frames(1) as buffers,
        TempPageReader(path, buffer=buffers[0]) as reader,
    ):
        actual = []
        while (row := reader.read()) is not None:
            actual.append(row)
    assert actual == rows
    assert pages.reserved_frames == set()
