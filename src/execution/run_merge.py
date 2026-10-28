import heapq
from collections.abc import Callable, Generator
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from src.execution.page_manager import SharedPageManager
from src.execution.temp_page_reader import TempPageReader
from src.execution.temp_page_writer import TempPageWriter

Row = tuple[int | str | float, ...]


def merge_runs(
    paths: list[Path],
    sort_key: Callable[[Row], Any],
    on_page_read: Callable[[int], None] | None = None,
    pages: SharedPageManager | None = None,
) -> Generator[Row, None, None]:
    """Merge sorted runs using shared page frames when provided."""

    with ExitStack() as stack:
        if pages is not None:
            if len(paths) > pages.capacity - 1:
                raise ValueError("Merge fan-in exceeds B - 1 input frames")

            buffers = stack.enter_context(pages.temporary_frames(len(paths)))
        else:
            buffers = [None] * len(paths)

        readers = [
            stack.enter_context(TempPageReader(path, buffer=buffer))
            for path, buffer in zip(paths, buffers, strict=True)
        ]

        heap: list[tuple[Any, int, Row]] = []

        for index, reader in enumerate(readers):
            before = reader.page_reads
            row = reader.read()

            if on_page_read is not None:
                on_page_read(reader.page_reads - before)

            if row is not None:
                heapq.heappush(
                    heap,
                    (sort_key(row), index, row),
                )

        while heap:
            _, index, row = heapq.heappop(heap)
            yield row

            before = readers[index].page_reads
            next_row = readers[index].read()

            if on_page_read is not None:
                on_page_read(readers[index].page_reads - before)

            if next_row is not None:
                heapq.heappush(
                    heap,
                    (sort_key(next_row), index, next_row),
                )


def merge_to_temp_run(
    paths: list[Path],
    sort_key: Callable[[Row], Any],
    temp_dir: Path,
    on_page_read: Callable[[int], None] | None = None,
    on_page_write: Callable[[int], None] | None = None,
    pages: SharedPageManager | None = None,
) -> Path:
    """Merge input runs into a new page-based temporary run."""

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix="sort_merge_",
        suffix=".tmp",
        dir=temp_dir,
        delete=False,
    ) as file:
        output_path = Path(file.name)

    try:
        with ExitStack() as stack:
            if pages is not None:
                if len(paths) > pages.capacity - 1:
                    raise ValueError("Merge fan-in exceeds B - 1 input frames")

                output_buffers = stack.enter_context(pages.temporary_frames(1))
                output_buffer = output_buffers[0]
            else:
                output_buffer = None

            writer = stack.enter_context(
                TempPageWriter(output_path, buffer=output_buffer)
            )

            for row in merge_runs(
                paths,
                sort_key,
                on_page_read=on_page_read,
                pages=pages,
            ):
                writer.write(row)

        if on_page_write is not None:
            on_page_write(writer.page_writes)

    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    return output_path
