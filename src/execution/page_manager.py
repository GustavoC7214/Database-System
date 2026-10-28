from collections.abc import Generator
from contextlib import contextmanager

from src.execution.page import PageKey
from src.storage.disk_manager import PAGE_SIZE, DiskManager


class SharedPageManager:
    """Manage a fixed number of page frames across database files."""

    def __init__(self, frames: int) -> None:
        if frames < 4:
            raise ValueError("Execution requires at least 4 frames")

        self.capacity = frames

        # Allocate the shared page buffers.
        self.frames = [bytearray(PAGE_SIZE) for _ in range(frames)]

        # Map each cached page to its frame index.
        self.page_table: dict[PageKey, int] = {}
        self.next_victim = 0

        self.pin_counts = [0] * frames

        # Frames reserved for temporary operator buffers.
        self.reserved_frames: set[int] = set()

        self.hits = 0
        self.reads = 0
        self.writes = 0

    def stats(self) -> dict[str, int]:
        """Return cumulative physical disk I/O counters."""
        return {
            "hits": self.hits,
            "reads": self.reads,
            "writes": self.writes,
        }

    def reserve_frames(self, count: int) -> list[int]:
        """Reserve unpinned frames for temporary operator buffers."""
        if count < 0:
            raise ValueError("Frame reservation count cannot be negative")

        available = [
            index
            for index in range(self.capacity)
            if index not in self.reserved_frames and self.pin_counts[index] == 0
        ]

        if len(available) < count:
            raise RuntimeError(
                f"Insufficient shared frames: requested {count}, "
                f"available {len(available)}"
            )

        selected = available[:count]

        for index in selected:
            old_key = next(
                (
                    key
                    for key, frame_index in self.page_table.items()
                    if frame_index == index
                ),
                None,
            )

            if old_key is not None:
                del self.page_table[old_key]

            self.reserved_frames.add(index)

        return selected

    def release_frames(self, indices: list[int]) -> None:
        """Release previously reserved temporary frames."""
        if len(indices) != len(set(indices)):
            raise ValueError("Duplicate frame indices")

        if any(index not in self.reserved_frames for index in indices):
            raise ValueError("Frame is not reserved")

        for index in indices:
            self.reserved_frames.remove(index)

    @contextmanager
    def temporary_frames(
        self,
        count: int,
    ) -> Generator[list[memoryview]]:
        """Temporarily reserve shared page buffers."""
        indices = self.reserve_frames(count)

        views = [memoryview(self.frames[index]) for index in indices]

        try:
            yield views
        finally:
            for view in views:
                view.release()

            self.release_frames(indices)

    def read_page(self, key: PageKey) -> memoryview:
        """Read a page, using the shared cache when available."""

        if key in self.page_table:
            self.hits += 1
            frame_index = self.page_table[key]
            return memoryview(self.frames[frame_index]).toreadonly()

        # Use the first available frame.
        used_frames = set(self.page_table.values())

        frame_index = next(
            (
                index
                for index in range(self.capacity)
                if index not in used_frames and index not in self.reserved_frames
            ),
            None,
        )

        if frame_index is None:
            # Find an unpinned frame using FIFO order.
            frame_index = None

            for offset in range(self.capacity):
                candidate = (self.next_victim + offset) % self.capacity

                if (
                    self.pin_counts[candidate] == 0
                    and candidate not in self.reserved_frames
                ):
                    frame_index = candidate
                    break

            if frame_index is None:
                raise RuntimeError("All shared page frames are pinned")

        disk = DiskManager(key.file_path)

        # Validate the requested page before invalidating a cached page.
        if key.page_id >= disk.page_count():
            raise ValueError(f"Invalid page ID: {key.page_id}")

        # Identify the page currently occupying the selected frame.
        old_key = next(
            (
                cached_key
                for cached_key, index in self.page_table.items()
                if index == frame_index
            ),
            None,
        )

        # Invalidate the old mapping before overwriting its frame.
        if old_key is not None:
            del self.page_table[old_key]

        # The previous mapping has already been invalidated.
        # If this read fails, the frame remains uncached.
        disk.read_page_into(key.page_id, self.frames[frame_index])

        if old_key is not None:
            self.next_victim = (frame_index + 1) % self.capacity

        self.page_table[key] = frame_index
        self.reads += 1

        return memoryview(self.frames[frame_index]).toreadonly()

    def pin_page(self, key: PageKey) -> None:
        """Prevent a cached page from being evicted."""

        if key not in self.page_table:
            raise ValueError(f"Page is not cached: {key}")

        frame_index = self.page_table[key]
        self.pin_counts[frame_index] += 1

    def unpin_page(self, key: PageKey) -> None:
        """Release one pin on a cached page."""

        if key not in self.page_table:
            raise ValueError(f"Page is not cached: {key}")

        frame_index = self.page_table[key]

        if self.pin_counts[frame_index] == 0:
            raise ValueError(f"Page is not pinned: {key}")

        self.pin_counts[frame_index] -= 1

    @contextmanager
    def pinned_page(self, key: PageKey) -> Generator[memoryview]:
        """Keep a page pinned while its data is being accessed."""
        view = self.read_page(key)
        self.pin_page(key)

        try:
            yield view
        finally:
            self.unpin_page(key)
            view.release()
