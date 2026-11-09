# Database System

A modular relational database management system built from scratch in Python for **COMP 3005** at Carleton University.

The project implements core database concepts across four modules: disk-based storage, relational query execution, SQL processing, and cost-based query optimization. A unified interactive SQL shell connects these modules into an executable database system.

## Features

- Persistent heap-file storage and table catalog
- Buffer pool with configurable page-replacement policies
- Binary record encoding and CSV loading
- Iterator-based physical query execution
- External sorting, grouping, and duplicate elimination
- Nested-loop, hash, and sort-merge joins
- SQL lexical analysis, parsing, and semantic validation
- Translation of SQL into logical query plans
- Logical-plan rewrites and statistics-based optimization
- Cost-based join ordering and physical operator selection
- Interactive SQL shell with query execution and I/O reporting
- Automated unit, integration, and regression tests

## System Architecture

The database is organized into four modules and an integration layer.

```text
SQL Query
    |
    v
Module 3: SQL Frontend
Lexer -> Parser -> Semantic Analysis -> Logical Plan
    |
    v
Module 4: Query Optimizer
Rewrites -> Statistics -> Cost Estimation -> Join Ordering
    |
    v
Module 2: Execution Engine
Physical Operators -> Iterator Execution
    |
    v
Module 1: Storage Engine
Buffer Pool -> Heap Files -> Disk Pages
    |
    v
Query Results
```

The integration layer provides the `dbshell` interface and coordinates the four modules.

For detailed implementation information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Project Structure

```text
Database-System/
├── dbshell                 # Unified interactive SQL shell
├── ra.py                   # Relational algebra entry point
├── exec                    # Physical-plan execution entry point
├── src/
│   ├── storage/            # Persistent storage and buffer management
│   ├── execution/          # Physical query operators and executor
│   ├── lexer/              # Lexical analysis
│   ├── parser/             # Parsing components
│   ├── engine/             # Relational algebra engine
│   ├── sql/                # SQL frontend
│   ├── optimizer/          # Query optimization
│   └── integration/        # Unified database engine and shell
├── tests/                  # Automated tests
├── experiments/            # Performance experiments
├── docs/                   # Module designs, reports, and design log
├── README.md
└── ARCHITECTURE.md
```

## Requirements

- Python 3.14 (development and testing environment)
- Git
- pytest (for automated testing)
- Ruff (for linting and formatting)
- Matplotlib (for the Module 2 crossover plotting script)

The database implementation uses Python and does not require a running PostgreSQL server for ordinary local execution.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/GustavoC7214/Database-System.git
cd Database-System
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install development dependencies

```bash
python3 -m pip install pytest ruff matplotlib
```

### 4. Start the database shell

```bash
python3 dbshell --db ./database --frames 32
```

The database directory is created automatically if it does not exist.

To leave the shell, enter:

```text
.quit
```

## SQL Examples

### Create a table

```sql
CREATE TABLE Employees (
    id INT,
    name VARCHAR(50),
    salary INT
);
```

### Insert records

```sql
INSERT INTO Employees VALUES (1, 'Alice', 75000);
INSERT INTO Employees VALUES (2, 'Bob', 65000);
INSERT INTO Employees VALUES (3, 'Charlie', 82000);
```

### Query records

```sql
SELECT * FROM Employees;
```

### Filter records

```sql
SELECT name, salary
FROM Employees
WHERE salary > 70000;
```

### Collect table statistics

```sql
ANALYZE Employees;
```

### Explain a query plan

```sql
EXPLAIN SELECT name
FROM Employees
WHERE salary > 70000;
```

### Explain and execute a query

```sql
EXPLAIN ANALYZE SELECT name
FROM Employees
WHERE salary > 70000;
```

This displays query results, estimated page I/O, measured page I/O, and execution counters.

### Change the memory budget

```sql
SET frames = 16;
```

The execution engine requires at least four buffer frames.

### Load data from CSV

```sql
LOAD Employees FROM 'employees.csv';
```

The CSV loader expects records matching the table schema, without a header row.


## SQL Support and Limitations

The unified SQL shell integrates the SQL frontend, query optimizer,
physical execution engine, and persistent storage layer.

### Supported SQL Features

The integrated execution path has automated test coverage for:

- `CREATE TABLE` and `INSERT INTO ... VALUES`
- `SELECT` with projection and filtering
- `SELECT DISTINCT`
- `ORDER BY` with ascending and descending ordering
- `LIMIT`
- `GROUP BY` and `HAVING`
- `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX`
- Aggregate output aliases
- `UNION` and `UNION ALL`
- `INTERSECT` and `EXCEPT`
- Supported equality joins
- Combined filtering, grouping, sorting, and limiting
- `ANALYZE`
- `EXPLAIN` and `EXPLAIN ANALYZE`
- `SET frames = n`
- `LOAD table FROM file`

Set operations validate column counts and compatible column types.
Their output column names follow the left input.

### Known Limitations

This project implements a restricted educational SQL dialect rather
than the complete SQL standard.

Not all syntactically valid queries can be translated into executable
physical plans.

Examples of limitations include:

- Unsupported complex expressions and some Boolean predicates
- Restricted physical join conditions
- Limited support for aliases and derived-table execution
- No complete transaction processing or crash recovery
- No general UPDATE, DELETE, or ALTER TABLE interface

Unsupported constructs produce explicit errors instead of silently
returning incorrect results.

For the supported grammar and additional restrictions, see
[SQL Grammar](docs/GRAMMAR_SQL.md).
results.

## Testing

Run the complete automated test suite:

```bash
python3 -m pytest tests/ -q
```

Run the integration tests:

```bash
python3 -m pytest tests/test_integration_shell.py -v
```

Check code quality:

```bash
python3 -m ruff check .
python3 -m ruff format --check .
```


Run the SQL integration regression tests:

```bash
python3 -m pytest \
  tests/test_integration_groupby.py \
  tests/test_integration_set_operations.py \
  tests/test_integration_sql_hardening.py \
  -v
```

### Latest Verified Results

As of November 8, 2026:

- **1,576 automated tests passed** in 24.48 seconds.
- **27 workload regression tests passed**.
- **25 of 25 integration benchmark queries completed successfully** with table statistics collected.
- Ruff linting passed.
- Ruff formatting passed.

These results validate the tested functionality, but do not guarantee
correctness for every SQL query or the assignment's unpublished workload.

## Experiments

The project includes experimental work for:

- **Module 1:** Storage and buffer-replacement behavior
- **Module 2:** Execution algorithm performance and memory-budget comparisons
- **Module 4:** Cardinality estimation, query rewrites, and optimization behavior

Results and analysis are documented in:

- [Module 1 Report](docs/REPORT_M1.md)
- [Module 2 Report](docs/REPORT_M2.md)
- [Module 4 Report](docs/REPORT_M4.md)

### Final Integration Benchmark

The project includes a reproducible 25-query integration workload
that exercises the unified SQL execution pipeline.

The benchmark creates three tables (Departments, Employees, and
Projects), populates them with test records, and collects table
statistics using ANALYZE before executing the workload.

Run the benchmark from the project root:

```bash
python3 -m experiments.integration.run_benchmark \
  --db /tmp/comp3005-final-benchmark \
  --setup experiments/integration/workload25_setup.sql \
  --workload experiments/integration/workload25.sql \
  --output experiments/integration/workload25_results.csv \
  --frames 16
```
Use a fresh database directory for each run because the setup script
creates tables.

The benchmark records query success, result row counts, measured and
estimated page I/O, physical and end-to-end execution time, estimated
and actual root cardinality, and root cardinality q-error.

### Verified Benchmark Results

On November 8, 2026:

- Queries executed: 25
- Successful queries: 25
- Failed queries: 0
- Buffer frames: 16

All 25 queries returned the expected number of rows.

This workload is a local regression benchmark, not the instructor's
unpublished final workload.

## Documentation

- [Architecture and Retrospective](ARCHITECTURE.md)
- [Design Log](docs/DESIGN_LOG.md)
- [Module 1 Design](docs/DESIGN_M1.md)
- [Module 2 Design](docs/DESIGN_M2.md)
- [Module 3 Design](docs/DESIGN_M3.md)
- [Module 4 Design](docs/DESIGN_M4.md)

## Academic Context

Developed for COMP 3005 at Carleton University.

The project emphasizes understanding how database components interact, including storage management, query execution, SQL translation, cardinality estimation, and physical query planning.

The implementation is an educational database system, not a production-ready replacement for PostgreSQL.
