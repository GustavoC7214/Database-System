"""Conservative fallback statistics for tables not yet analyzed.

These estimates are used only for query planning. They are not
persisted and do not replace statistics collected by ANALYZE.
"""

from src.optimizer.statistics import TableStatistics

DEFAULT_ROWS = 1000
DEFAULT_PAGES = 20
DEFAULT_WIDTH = 32.0


def fallback_table_statistics(table: str) -> TableStatistics:
    """Create deterministic planning estimates for an unanalyzed table."""
    return TableStatistics(
        table=table,
        n_tuples=DEFAULT_ROWS,
        n_pages=DEFAULT_PAGES,
        width=DEFAULT_WIDTH,
    )


def complete_statistics(
    tables: set[str],
    statistics: dict[str, TableStatistics],
) -> dict[str, TableStatistics]:
    """Return statistics for every referenced table.

    Existing ANALYZE results are preserved. Missing tables receive
    temporary conservative estimates.

    This function never mutates the input dictionary or writes
    statistics to disk.
    """
    completed = dict(statistics)

    for table in sorted(tables):
        if table not in completed:
            completed[table] = fallback_table_statistics(table)

    return completed
