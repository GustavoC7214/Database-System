class MemoryBudget:
    """Track frame reservations across an execution plan."""

    def __init__(self, frames: int) -> None:
        if frames < 4:
            raise ValueError("Execution requires at least 4 frames")

        self.capacity = frames
        self.used = 0
        self.peak = 0

    @property
    def available(self) -> int:
        return self.capacity - self.used

    def acquire(self, frames: int) -> None:
        if frames < 0:
            raise ValueError("Cannot acquire a negative number of frames")

        if frames > self.available:
            raise RuntimeError(
                f"Memory budget exceeded: requested {frames} frames, "
                f"only {self.available} available"
            )

        self.used += frames
        self.peak = max(self.peak, self.used)

    def release(self, frames: int) -> None:
        if frames < 0:
            raise ValueError("Cannot release a negative number of frames")

        if frames > self.used:
            raise RuntimeError("Cannot release more frames than acquired")

        self.used -= frames
