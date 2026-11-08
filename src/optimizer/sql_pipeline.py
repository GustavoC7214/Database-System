"""SQL compilation with optional logical and join-order optimization."""

from typing import Any

from src.optimizer.pipeline import optimize_logical_plan
from src.optimizer.sql_join_order import optimize_sql_join_order
from src.optimizer.statistics import TableStatistics
from src.sql.compiler import SQLCompiler

Plan = dict[str, Any]


def compile_optimized_sql(
    source: str,
    compiler: SQLCompiler,
    statistics: dict[str, TableStatistics],
    *,
    table_columns: dict[str, list[str]],
    frames: int = 32,
    enable_join_ordering: bool = True,
    enable_logical_rewrites: bool = False,
) -> list[Plan]:
    """Compile SQL and apply requested optimization stages.

    Logical rewrites run before DP join ordering when enabled.

    This function returns logical plans, not executable physical plans.
    Unsupported join trees retain their existing structure.
    """
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("Buffer frames must be an integer")
    if frames < 3:
        raise ValueError("At least three buffer frames are required")

    plans = compiler.compile_sql(source)
    results: list[Plan] = []

    for plan in plans:
        current = plan

        if enable_logical_rewrites:
            current = optimize_logical_plan(
                current,
                table_columns=table_columns,
            )

        if enable_join_ordering:
            current = optimize_sql_join_order(
                current,
                statistics,
                table_columns=table_columns,
                frames=frames,
            )

        results.append(current)

    return results
