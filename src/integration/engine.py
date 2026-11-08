"""Integration of SQL, optimizer, executor, and persistent storage."""

from dataclasses import dataclass
from pathlib import Path

from src.execution.plan_executor import PhysicalPlanExecutor
from src.optimizer.analyze import analyze_table
from src.optimizer.physical_lowering import lower_physical_plan
from src.optimizer.plan_cost import PhysicalCostEstimator
from src.optimizer.statistics import StatisticsStore
from src.optimizer.statistics_fallback import complete_statistics
from src.sql import ast
from src.sql.catalog import SchemaCatalog
from src.sql.compiler import SQLCompiler
from src.sql.parser import parse_sql
from src.storage.catalog import Catalog
from src.storage.csv_loader import load_csv
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


@dataclass
class QueryResult:
    message: str
    columns: list[str] | None = None
    rows: list[tuple] | None = None
    estimated_io: float | None = None
    actual_io: int | None = None
    counters: dict | None = None


class DatabaseEngine:
    def __init__(self, db_dir: str | Path, frames: int = 32):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.set_frames(frames)

    def set_frames(self, frames: int) -> None:
        if isinstance(frames, bool) or not isinstance(frames, int):
            raise TypeError("Frame count must be an integer")
        if frames < 4:
            raise ValueError("At least four buffer frames are required")
        self.frames = frames

    def create_table(self, statement: ast.CreateTable) -> QueryResult:
        definitions = []
        for column in statement.columns:
            if column.data_type == "INT":
                kind = "INT"
            elif column.data_type == "VARCHAR" and column.length is not None:
                kind = f"VARCHAR({column.length})"
            else:
                raise ValueError(f"Unsupported column type: {column.data_type}")
            definitions.append(f"{column.name}:{kind}")

        Catalog(self.db_dir).create_table(statement.name, ",".join(definitions))
        return QueryResult(f"Created table {statement.name}")

    def insert(self, statement: ast.Insert) -> QueryResult:
        catalog = Catalog(self.db_dir)
        metadata = catalog.get_table(statement.table)
        values = tuple(literal.value for literal in statement.values)

        # Encode before modifying the heap, so invalid records are rejected.
        encoded = encode_record(values, metadata.schema)
        heap = HeapFile(self.db_dir / metadata.filename, frames=self.frames)
        heap.insert(encoded)
        heap.flush()

        metadata.page_count = heap.page_count
        metadata.tuple_count += 1
        catalog.update_table(metadata)

        return QueryResult("Inserted 1 row")

    def load(self, table: str, filename: str) -> QueryResult:
        count = load_csv(self.db_dir, table, filename, frames=self.frames)
        return QueryResult(f"Loaded {count} rows into {table}")

    def analyze(self, table: str) -> QueryResult:
        analyze_table(
            str(self.db_dir),
            table,
            buckets=20,
            frames=self.frames,
        )
        return QueryResult(f"Analyzed table {table}")

    def query(
        self,
        statement: ast.Query,
        *,
        explain: bool = False,
        execute: bool = True,
    ) -> QueryResult:
        catalog = SchemaCatalog.from_directory(str(self.db_dir))
        compiler = SQLCompiler(catalog)
        logical = compiler.compile(statement)

        def tables_in(node):
            found = set()
            if node.get("op") == "scan":
                found.add(node["table"])
            for key in ("child", "left", "right"):
                child = node.get(key)
                if isinstance(child, dict):
                    found.update(tables_in(child))
            return found

        tables = tables_in(logical)
        columns = {
            name: [col.name for col in catalog.get_table(name).columns]
            for name in tables
        }
        store = StatisticsStore(self.db_dir)
        stored = {
            name: stats for name in tables if (stats := store.load(name)) is not None
        }
        statistics = complete_statistics(tables, stored)

        # Apply only transformations already supported by the optimizer.
        from src.optimizer.pipeline import optimize_logical_plan
        from src.optimizer.sql_join_order import optimize_sql_join_order

        plan = optimize_logical_plan(logical, table_columns=columns)
        plan = optimize_sql_join_order(
            plan, statistics, table_columns=columns, frames=self.frames
        )

        physical = lower_physical_plan(
            plan,
            statistics,
            table_columns=columns,
            frames=self.frames,
        )

        estimated = None
        if explain:
            estimated = (
                PhysicalCostEstimator(
                    statistics,
                    frames=self.frames,
                    table_columns=columns,
                )
                .estimate(plan)
                .total_io
            )

        if not execute:
            return QueryResult(
                message=f"Physical plan:\n{__import__('json').dumps(physical, indent=2)}",
                estimated_io=estimated,
            )

        result = PhysicalPlanExecutor(self.db_dir, frames=self.frames).execute(physical)

        counters = result.counters
        return QueryResult(
            message=f"Returned {len(result.rows)} rows",
            columns=[name for name, _ in result.schema],
            rows=result.rows,
            estimated_io=estimated,
            actual_io=counters["page_reads"] + counters["page_writes"],
            counters=counters,
        )

    def execute_sql(self, source: str) -> list[QueryResult]:
        results = []
        for statement in parse_sql(source):
            if isinstance(statement, ast.CreateTable):
                results.append(self.create_table(statement))
            elif isinstance(statement, ast.Insert):
                results.append(self.insert(statement))
            elif isinstance(statement, (ast.Select, ast.SetOperation)):
                results.append(self.query(statement))
            else:
                raise TypeError(
                    f"Unsupported SQL statement: {type(statement).__name__}"
                )
        return results
