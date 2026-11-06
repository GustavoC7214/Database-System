"""Persistent statistics for the Module 4 query optimizer."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

StatisticValue = int | str

STATISTICS_VERSION = 1


@dataclass(frozen=True, slots=True)
class HistogramBucket:
    """One bucket of an equi-depth column histogram."""

    lower: StatisticValue
    upper: StatisticValue
    count: int
    ndv: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("Histogram bucket count must be positive")
        if not 1 <= self.ndv <= self.count:
            raise ValueError("Invalid histogram bucket NDV")
        if type(self.lower) is not type(self.upper):
            raise ValueError("Histogram boundaries must have matching types")
        if self.lower > self.upper:
            raise ValueError("Histogram lower boundary exceeds upper boundary")


@dataclass(frozen=True, slots=True)
class ColumnStatistics:
    """Statistics describing a single table column."""

    ndv: int
    minimum: StatisticValue | None
    maximum: StatisticValue | None
    histogram: tuple[HistogramBucket, ...] = ()

    def __post_init__(self) -> None:
        if self.ndv < 0:
            raise ValueError("Column NDV cannot be negative")

        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("Column minimum and maximum must both be present")

        if self.ndv == 0:
            if self.minimum is not None or self.histogram:
                raise ValueError("Empty column must have empty statistics")
        else:
            if self.minimum is None or self.maximum is None:
                raise ValueError("Nonempty column requires min and max")
            if type(self.minimum) is not type(self.maximum):
                raise ValueError("Column extrema must have matching types")
            if self.minimum > self.maximum:
                raise ValueError("Column minimum exceeds maximum")


@dataclass(frozen=True, slots=True)
class TableStatistics:
    """Statistics collected by ANALYZE for a table."""

    table: str
    n_tuples: int
    n_pages: int
    width: float
    columns: dict[str, ColumnStatistics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.table or not self.table.isascii() or not self.table.isidentifier():
            raise ValueError("Invalid statistics table name")
        if self.n_tuples < 0:
            raise ValueError("Tuple count cannot be negative")
        if self.n_pages < 0:
            raise ValueError("Page count cannot be negative")
        if not 0 <= self.width < float("inf"):
            raise ValueError("Average record width must be finite and nonnegative")
        if self.n_tuples == 0 and self.width != 0:
            raise ValueError("Empty table must have zero average width")


class StatisticsStore:
    """Store optimizer statistics independently of catalog record size.

    Files are written to <db_dir>/optimizer_stats/<table>.json.
    The existing Module 1 catalog remains unchanged.
    """

    def __init__(self, db_dir: str | Path) -> None:
        self.db_dir = Path(db_dir)
        self.stats_dir = self.db_dir / "optimizer_stats"

    def _path(self, table: str) -> Path:
        if not table or not table.isascii() or not table.isidentifier():
            raise ValueError(f"Invalid table name: {table}")
        return self.stats_dir / f"{table}.json"

    def save(self, statistics: TableStatistics) -> None:
        """Atomically replace a table's persisted statistics."""
        if not self.db_dir.is_dir():
            raise ValueError(f"Database directory does not exist: {self.db_dir}")

        destination = self._path(statistics.table)
        self.stats_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": STATISTICS_VERSION,
            **asdict(statistics),
        }

        encoded = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.stats_dir,
                prefix=f".{statistics.table}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())

            os.replace(temporary_path, destination)

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load(self, table: str) -> TableStatistics | None:
        """Load statistics, returning None if ANALYZE has not run."""
        path = self._path(table)

        if not path.is_file():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))

        if payload.get("version") != STATISTICS_VERSION:
            raise ValueError(f"Unsupported statistics version for table {table}")

        if payload.get("table") != table:
            raise ValueError("Statistics table name mismatch")

        columns = {}

        for name, column in payload["columns"].items():
            buckets = tuple(HistogramBucket(**bucket) for bucket in column["histogram"])

            columns[name] = ColumnStatistics(
                ndv=column["ndv"],
                minimum=column["minimum"],
                maximum=column["maximum"],
                histogram=buckets,
            )

        return TableStatistics(
            table=payload["table"],
            n_tuples=payload["n_tuples"],
            n_pages=payload["n_pages"],
            width=payload["width"],
            columns=columns,
        )

    def delete(self, table: str) -> None:
        """Delete stored statistics for a table, if present."""
        self._path(table).unlink(missing_ok=True)
