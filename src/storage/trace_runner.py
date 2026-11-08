"""Utilities for replaying buffer pool access traces."""

from pathlib import Path

from src.storage.buffer_pool import BufferPool
from src.storage.disk_manager import DiskManager


def read_trace(trace_path: str | Path) -> list[int]:
    """Read one nonnegative page ID per line."""
    page_ids: list[int] = []

    with open(trace_path, encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()

            if not text or text.startswith("#"):
                continue

            try:
                page_id = int(text)
            except ValueError as exc:
                raise ValueError(
                    f"Trace line {line_number}: invalid page ID {text!r}"
                ) from exc

            if page_id < 0:
                raise ValueError(
                    f"Trace line {line_number}: page ID cannot be negative"
                )

            page_ids.append(page_id)

    return page_ids


def run_trace(
    db_dir: str | Path,
    trace_path: str | Path,
    frames: int = 16,
    policy: str = "lru",
) -> dict[str, int]:
    """Replay page accesses and return buffer pool statistics."""
    if frames < 1:
        raise ValueError("Buffer pool must have at least one frame")

    if policy not in {"lru", "clock"}:
        raise ValueError(f"Unknown replacement policy: {policy}")

    page_ids = read_trace(trace_path)

    db_path = Path(db_dir)
    db_path.mkdir(parents=True, exist_ok=True)

    # Use a separate file for trace simulation.
    disk = DiskManager(db_path / "trace_pages.db")

    # Ensure every page referenced by the trace exists.
    if page_ids:
        required_pages = max(page_ids) + 1

        while disk.page_count() < required_pages:
            disk.allocate_page()

    pool = BufferPool(
        disk=disk,
        frames=frames,
        policy=policy,
    )

    for page_id in page_ids:
        pool.fetch_page(page_id)
        pool.unpin_page(page_id)

    return pool.stats()
