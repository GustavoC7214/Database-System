from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PageKey:
    """Uniquely identify a page across database files."""

    file_path: Path
    page_id: int

    def __post_init__(self) -> None:
        if self.page_id < 0:
            raise ValueError("Page ID cannot be negative")
