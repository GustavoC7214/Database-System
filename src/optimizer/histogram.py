"""Deterministic equi-depth histograms over sorted value streams."""

from collections.abc import Iterable

from src.optimizer.statistics import (
    ColumnStatistics,
    HistogramBucket,
    StatisticValue,
)


def build_column_statistics(
    values: Iterable[StatisticValue],
    n_tuples: int,
    buckets: int = 20,
) -> ColumnStatistics:
    """Summarize sorted, non-null values without materializing the stream.

    Bucket boundaries are determined by tuple ranks. Duplicate values
    can occur in adjacent buckets.
    """
    if n_tuples < 0:
        raise ValueError("Tuple count cannot be negative")
    if buckets < 1:
        raise ValueError("Bucket count must be positive")

    if n_tuples == 0:
        if any(True for _ in values):
            raise ValueError("Expected an empty value stream")
        return ColumnStatistics(
            ndv=0,
            minimum=None,
            maximum=None,
        )

    bucket_count = min(buckets, n_tuples)
    result: list[HistogramBucket] = []

    first: StatisticValue | None = None
    last: StatisticValue | None = None
    previous: StatisticValue | None = None
    global_ndv = 0

    current_bucket = -1
    bucket_lower: StatisticValue | None = None
    bucket_upper: StatisticValue | None = None
    bucket_rows = 0
    bucket_ndv = 0
    bucket_previous: StatisticValue | None = None

    def finish_bucket() -> None:
        if bucket_rows == 0:
            return

        assert bucket_lower is not None
        assert bucket_upper is not None

        result.append(
            HistogramBucket(
                lower=bucket_lower,
                upper=bucket_upper,
                count=bucket_rows,
                ndv=bucket_ndv,
            )
        )

    observed = 0

    for value in values:
        if observed >= n_tuples:
            raise ValueError("More values than expected")

        if first is None:
            first = value

        if previous is not None and value < previous:
            raise ValueError("Histogram input must be sorted")

        if previous is None or value != previous:
            global_ndv += 1

        # Distribute n tuples across k buckets, with sizes differing
        # by no more than one tuple.
        target_bucket = ((observed + 1) * bucket_count - 1) // n_tuples

        if target_bucket != current_bucket:
            finish_bucket()
            current_bucket = target_bucket
            bucket_lower = value
            bucket_rows = 0
            bucket_ndv = 0
            bucket_previous = None

        bucket_upper = value
        bucket_rows += 1

        if bucket_previous is None or value != bucket_previous:
            bucket_ndv += 1

        bucket_previous = value
        previous = value
        last = value
        observed += 1

    if observed != n_tuples:
        raise ValueError(f"Expected {n_tuples} values, received {observed}")

    finish_bucket()

    assert first is not None
    assert last is not None

    return ColumnStatistics(
        ndv=global_ndv,
        minimum=first,
        maximum=last,
        histogram=tuple(result),
    )
