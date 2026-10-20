
from dataclasses import dataclass, field

from src.storage.disk_manager import PAGE_SIZE, DiskManager


@dataclass
class BufferFrame:
    page_id: int | None = None
    data: bytearray = field(
        default_factory=lambda: bytearray(PAGE_SIZE)
    )
    pin_count: int = 0
    dirty: bool = False
    reference_bit: bool = False
    last_access: int = 0


class BufferPool:
    def __init__(self, disk: DiskManager, frames: int, policy: str = "lru") -> None:
        if frames <= 0:
            raise ValueError("Buffer pool must have at least one frame")

        if policy not in {"lru", "clock"}:
            raise ValueError(f"Unknown replacement policy: {policy}")

        self.disk = disk
        self.capacity = frames
        self.policy = policy

        self.frames = [BufferFrame() for _ in range(frames)]
        self.page_table: dict[int, int] = {}

        self.clock_hand = 0
        self.access_counter = 0

        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.reads = 0
        self.writes = 0

    def stats(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "reads": self.reads,
            "writes": self.writes,
        }

    def fetch_page(self, page_id: int) -> bytearray:
        if page_id in self.page_table:
            self.access_counter += 1
            self.hits += 1

            frame = self.frames[self.page_table[page_id]]
            frame.pin_count += 1
            frame.last_access = self.access_counter
            frame.reference_bit = True

            return frame.data

        data = self.disk.read_page(page_id)

        frame_index = self._select_victim()
        frame = self.frames[frame_index]

        self.access_counter += 1

        if frame.page_id is not None:
            if frame.dirty:
                self.disk.write_page(frame.page_id, bytes(frame.data))
                self.writes += 1

            del self.page_table[frame.page_id]
            self.evictions += 1

        frame.page_id = page_id
        frame.data = bytearray(data)
        frame.pin_count = 1
        frame.dirty = False
        frame.reference_bit = True
        frame.last_access = self.access_counter

        self.page_table[page_id] = frame_index

        self.misses += 1
        self.reads += 1

        return frame.data

    def unpin_page(self, page_id: int, dirty: bool = False) -> None:
        if page_id not in self.page_table:
            raise ValueError(f"Page {page_id} is not in the buffer pool")

        frame = self.frames[self.page_table[page_id]]

        if frame.pin_count == 0:
            raise ValueError(f"Page {page_id} is already unpinned")

        frame.pin_count -= 1
        frame.dirty = frame.dirty or dirty

    def flush_all(self) -> None:
        for frame in self.frames:
            if frame.page_id is None or not frame.dirty:
                continue

            self.disk.write_page(frame.page_id, bytes(frame.data))
            self.writes += 1
            frame.dirty = False

    def new_page(self) -> tuple[int, bytearray]:
        frame_index = self._select_victim()
        frame = self.frames[frame_index]

        page_id = self.disk.allocate_page()

        if frame.page_id is not None:
            if frame.dirty:
                self.disk.write_page(
                    frame.page_id,
                    bytes(frame.data),
                )
                self.writes += 1

            del self.page_table[frame.page_id]
            self.evictions += 1

        self.access_counter += 1

        frame.page_id = page_id
        frame.data = bytearray(PAGE_SIZE)
        frame.pin_count = 1
        frame.dirty = True
        frame.reference_bit = True
        frame.last_access = self.access_counter

        self.page_table[page_id] = frame_index

        return page_id, frame.data

    def _select_victim(self) -> int:
        if self.policy == "clock":
            return self._select_clock_victim()

        return self._select_lru_victim()

    def _select_lru_victim(self) -> int:
        for index, frame in enumerate(self.frames):
            if frame.page_id is None:
                return index

        candidates = [
            (frame.last_access, index)
            for index, frame in enumerate(self.frames)
            if frame.pin_count == 0
        ]

        if not candidates:
            raise RuntimeError("All buffer pool frames are pinned")

        _, frame_index = min(candidates)
        return frame_index

    def _select_clock_victim(self) -> int:
        for _ in range(self.capacity):
            index = self.clock_hand
            frame = self.frames[index]

            if frame.page_id is None:
                self.clock_hand = (index + 1) % self.capacity
                return index

            self.clock_hand = (index + 1) % self.capacity

        if all(frame.pin_count > 0 for frame in self.frames):
            raise RuntimeError("All buffer pool frames are pinned")

        while True:
            index = self.clock_hand
            frame = self.frames[index]

            self.clock_hand = (index + 1) % self.capacity

            if frame.pin_count > 0:
                continue

            if frame.reference_bit:
                frame.reference_bit = False
                continue

            return index
