import pytest

from src.execution.page_manager import SharedPageManager


def test_reserve_and_release_frames():
    pages = SharedPageManager(frames=4)

    reserved = pages.reserve_frames(3)

    assert len(reserved) == 3
    assert len(pages.reserved_frames) == 3

    with pytest.raises(RuntimeError, match="Insufficient"):
        pages.reserve_frames(2)

    pages.release_frames(reserved)

    assert pages.reserved_frames == set()
    assert len(pages.reserve_frames(4)) == 4


def test_reject_invalid_reservations():
    pages = SharedPageManager(frames=4)

    with pytest.raises(ValueError):
        pages.reserve_frames(-1)

    with pytest.raises(ValueError):
        pages.release_frames([0])

    reserved = pages.reserve_frames(2)

    with pytest.raises(ValueError):
        pages.release_frames([reserved[0], reserved[0]])

    pages.release_frames(reserved)


def test_reserved_frames_are_unique():
    pages = SharedPageManager(frames=4)

    first = pages.reserve_frames(2)
    second = pages.reserve_frames(2)

    assert set(first).isdisjoint(second)
    assert len(pages.reserved_frames) == 4

    pages.release_frames(first)
    pages.release_frames(second)

    assert not pages.reserved_frames


def test_temporary_frames_release_automatically():
    pages = SharedPageManager(frames=4)

    with pages.temporary_frames(3) as buffers:
        assert len(buffers) == 3
        assert len(pages.reserved_frames) == 3

        for buffer in buffers:
            assert len(buffer) == 4096

        buffers[0][:4] = b"TEST"

    assert pages.reserved_frames == set()


def test_temporary_frames_release_after_exception():
    pages = SharedPageManager(frames=4)

    with (
        pytest.raises(ValueError, match="intentional"),
        pages.temporary_frames(4) as buffers,
    ):
        buffers[0][:4] = b"TEST"
        raise ValueError("intentional")

    assert pages.reserved_frames == set()
    assert len(pages.reserve_frames(4)) == 4
