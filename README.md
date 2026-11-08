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

The SQL frontend supports a broader grammar than the integrated physical executor.

The unified shell has been tested with:

- `CREATE TABLE`
- `INSERT INTO ... VALUES`
- Basic `SELECT` queries
- Projection and column-to-literal filtering
- `ANALYZE`
- `EXPLAIN`
- `EXPLAIN ANALYZE`
- `SET frames = n`
- `LOAD table FROM file`

The execution engine also implements join, sort, grouping, and set-operation algorithms. However, not every SQL construct can currently be translated into an executable physical plan.

For example, aggregate queries with `GROUP BY` are not yet supported through the unified SQL-to-physical-plan path.

Unsupported physical plans produce explicit errors rather than silently returning incorrect results.

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

### Latest Verified Results

As of November 8, 2026:

- **1,490 automated tests passed**
- **20 integration tests passed**
- Ruff linting passed
- Ruff formatting passed

These results cover the implemented and tested functionality; they do not guarantee correctness for every possible SQL query or the assignment's unpublished workload.

## Experiments

The project includes experimental work for:

- **Module 1:** Storage and buffer-replacement behavior
- **Module 2:** Execution algorithm performance and memory-budget comparisons
- **Module 4:** Cardinality estimation, query rewrites, and optimization behavior

Results and analysis are documented in:

- [Module 1 Report](docs/REPORT_M1.md)
- [Module 2 Report](docs/REPORT_M2.md)
- [Module 4 Report](docs/REPORT_M4.md)

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
