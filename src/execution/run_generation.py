"""Generate sorted temporary runs using shared page frames."""

import json
import struct
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.temp_page import PAYLOAD_SIZE
from src.execution.temp_page_writer import TempPageWriter
from src.execution.temp_run import tuple_size

Row = tuple[int | str | float, ...]


def generate_sorted_runs(
    child: Operator,
    memory_pages: int,
    sort_key: Callable[[Row], Any],
    temp_dir: Path,
    on_page_write: Callable[[int], None] | None = None,
    pages: SharedPageManager | None = None,
) -> list[Path]:
    """Generate sorted runs using a bounded number of pages."""
    if memory_pages < 1:
        raise ValueError("Run generation requires at least one memory page")

    if pages is None:
        # Preserve the original interface for existing callers.
        return _generate_legacy_runs(
            child,
            memory_pages,
            sort_key,
            temp_dir,
            on_page_write,
        )

    if memory_pages > pages.capacity:
        raise ValueError("Memory pages exceed shared frame capacity")

    if memory_pages < 4:
        raise ValueError("Shared run generation requires at least 4 frames")

    run_frame_count = memory_pages - 2
    runs: list[Path] = []

    # Reserve run frames and one output frame, leaving one
    # frame available for the child operator.
    with pages.temporary_frames(run_frame_count + 1) as buffers:
        run_buffers = buffers[:run_frame_count]
        output_buffer = buffers[-1]

        records: list[tuple[int, int, int]] = []
        used = [0] * run_frame_count
        current_frame = 0

        def flush_run() -> None:
            nonlocal current_frame

            if not records:
                return

            rows: list[Row] = []

            for frame_index, offset, length in records:
                encoded = bytes(run_buffers[frame_index][offset : offset + length])
                decoded = json.loads(encoded.decode("utf-8"))
                rows.append(tuple(decoded))

            rows.sort(key=sort_key)

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="sort_run_",
                suffix=".tmp",
                dir=temp_dir,
                delete=False,
            ) as file:
                path = Path(file.name)

            try:
                with TempPageWriter(
                    path,
                    buffer=output_buffer,
                ) as writer:
                    for row in rows:
                        writer.write(row)
            except Exception:
                path.unlink(missing_ok=True)
                raise

            if on_page_write is not None:
                on_page_write(writer.page_writes)

            runs.append(path)
            records.clear()
            used[:] = [0] * run_frame_count
            current_frame = 0

        while (row := child.next()) is not None:
            encoded = json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            size = 4 + len(encoded)

            if size > PAYLOAD_SIZE:
                raise ValueError("Tuple exceeds temporary-page capacity")

            if used[current_frame] + size > PAYLOAD_SIZE:
                if current_frame + 1 < run_frame_count:
                    current_frame += 1
                else:
                    flush_run()

            offset = used[current_frame]

            struct.pack_into(
                "<I",
                run_buffers[current_frame],
                offset,
                len(encoded),
            )
            run_buffers[current_frame][offset + 4 : offset + size] = encoded

            records.append((current_frame, offset + 4, len(encoded)))
            used[current_frame] += size

        flush_run()

    return runs


def _generate_legacy_runs(
    child: Operator,
    memory_pages: int,
    sort_key: Callable[[Row], Any],
    temp_dir: Path,
    on_page_write: Callable[[int], None] | None,
) -> list[Path]:
    """Retain compatibility with existing direct callers."""
    runs: list[Path] = []
    batch: list[Row] = []
    used_pages = 0
    current_page_bytes = 0

    def flush_batch() -> None:
        if not batch:
            return

        batch.sort(key=sort_key)

        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="sort_run_",
            suffix=".tmp",
            dir=temp_dir,
            delete=False,
        ) as file:
            path = Path(file.name)

        try:
            with TempPageWriter(path) as writer:
                for batch_row in batch:
                    writer.write(batch_row)
        except Exception:
            path.unlink(missing_ok=True)
            raise

        if on_page_write is not None:
            on_page_write(writer.page_writes)

        runs.append(path)
        batch.clear()

    while (row := child.next()) is not None:
        size = tuple_size(row)

        if size > PAYLOAD_SIZE:
            raise ValueError("Tuple exceeds temporary-page capacity")

        needs_new_page = used_pages == 0 or current_page_bytes + size > PAYLOAD_SIZE

        if needs_new_page and used_pages >= memory_pages:
            flush_batch()
            used_pages = 0
            current_page_bytes = 0

        if used_pages == 0:
            used_pages = 1
            current_page_bytes = 0
        elif current_page_bytes + size > PAYLOAD_SIZE:
            used_pages += 1
            current_page_bytes = 0

        batch.append(row)
        current_page_bytes += size

    flush_batch()
    return runs
