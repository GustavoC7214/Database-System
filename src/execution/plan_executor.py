"""Execute physical plans and collect results and statistics."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.execution.operator import Operator
from src.execution.page_manager import SharedPageManager
from src.execution.physical_plan import PhysicalPlanBuilder

Row = tuple[int | str | float, ...]


@dataclass
class ExecutionResult:
    schema: list[tuple[str, str]]
    rows: list[Row]
    counters: dict[str, int]
    operator_stats: list[dict[str, Any]] | None = None
    buffer_stats: dict[str, int] | None = None


class PhysicalPlanExecutor:
    """Execute a JSON physical plan using a shared page manager."""

    def __init__(
        self,
        db_dir: str | Path,
        frames: int = 4,
    ) -> None:
        self.pages = SharedPageManager(frames)
        self.builder = PhysicalPlanBuilder(db_dir, self.pages)

    def execute(self, plan: dict) -> ExecutionResult:
        root = self.builder.build(plan)
        return self.execute_operator(root)

    def execute_json(self, text: str) -> ExecutionResult:
        root = self.builder.from_json(text)
        return self.execute_operator(root)

    def execute_file(self, path: str | Path) -> ExecutionResult:
        root = self.builder.from_file(path)
        return self.execute_operator(root)

    def execute_operator(self, root: Operator) -> ExecutionResult:
        rows: list[Row] = []
        before = self.pages.stats()

        try:
            root.open()
            schema = list(root.schema)

            while (row := root.next()) is not None:
                rows.append(row)
        finally:
            root.close()

        after = self.pages.stats()

        buffer_stats = {key: after[key] - before[key] for key in before}

        operator_stats = self.collect_operator_stats(root)

        return ExecutionResult(
            schema=schema,
            rows=rows,
            counters=self.aggregate_counters(operator_stats),
            operator_stats=operator_stats,
            buffer_stats=buffer_stats,
        )

    @staticmethod
    def collect_operator_stats(root: Operator) -> list[dict[str, Any]]:
        """Collect each operator's own counters without summing them."""
        stats: list[dict[str, Any]] = []
        visited: set[int] = set()

        def visit(operator: Operator, depth: int) -> None:
            if id(operator) in visited:
                return

            visited.add(id(operator))

            stats.append(
                {
                    "operator": type(operator).__name__,
                    "depth": depth,
                    "counters": operator.counters(),
                }
            )

            for attribute in ("child", "left", "right"):
                child = getattr(operator, attribute, None)

                if isinstance(child, Operator):
                    visit(child, depth + 1)

        visit(root, 0)
        return stats

    @staticmethod
    def aggregate_counters(
        operator_stats: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Aggregate execution counters across the operator tree."""
        totals = {
            "tuples_out": 0,
            "comparisons": 0,
            "page_reads": 0,
            "page_writes": 0,
        }

        if not operator_stats:
            return totals

        # Only the root operator's output is the final query output.
        totals["tuples_out"] = operator_stats[0]["counters"]["tuples_out"]

        # Comparisons and I/O are accumulated across all operators.
        for entry in operator_stats:
            counters = entry["counters"]
            totals["comparisons"] += counters["comparisons"]
            totals["page_reads"] += counters["page_reads"]
            totals["page_writes"] += counters["page_writes"]

        return totals
