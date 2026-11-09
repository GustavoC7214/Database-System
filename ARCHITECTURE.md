# Database System Architecture

## 1. Overview

This project implements a modular relational database system in Python. It is organized into four independently developed modules connected through a unified integration layer.

The primary architectural objective is to separate persistent storage, physical query execution, SQL processing, and query optimization while defining clear interfaces between them.

Each module can be tested independently, and the integration layer coordinates them without replacing their existing implementations.

## 2. End-to-End Architecture

```text
                  User
                   |
              SQL Statement
                   |
                   v
          +------------------+
          | Integration      |
          | dbshell          |
          | DatabaseEngine   |
          +------------------+
                   |
                   v
          +------------------+
          | Module 3         |
          | SQL Frontend     |
          | Lexer / Parser   |
          | Semantic Checks  |
          +------------------+
                   |
              Logical Plan
                   |
                   v
          +------------------+
          | Module 4         |
          | Query Optimizer  |
          | Rewrites         |
          | Statistics       |
          | Join Ordering    |
          | Cost Model       |
          +------------------+
                   |
              Physical Plan
                   |
                   v
          +------------------+
          | Module 2         |
          | Execution Engine |
          | Iterator Tree    |
          | Physical Ops     |
          +------------------+
                   |
              Page Access
                   |
                   v
          +------------------+
          | Module 1         |
          | Storage Engine   |
          | Buffer Pool      |
          | Heap Files       |
          | Catalog          |
          +------------------+
                   |
                Disk
```

The catalog and collected table statistics provide metadata to the SQL frontend and optimizer.

## 3. Module 1 — Storage Engine

### Responsibilities

Module 1 provides persistent storage for database records and metadata.

Its principal responsibilities include:

- Managing fixed-size disk pages
- Storing records in heap files
- Encoding and decoding records
- Maintaining the database catalog
- Tracking table schemas and record counts
- Buffering page access
- Supporting configurable page replacement
- Loading records from CSV files

### Main Components

The storage package includes:

- `catalog.py`
- `heap_file.py`
- `record_codec.py`
- `csv_loader.py`

Additional storage components implement page and buffer management.

### Storage Interface

The catalog provides access to table metadata, including:

- Table name
- Storage filename
- Column schema
- Page count
- Tuple count

Heap files support insertion, scanning, and retrieval of stored records.

The integration layer uses these interfaces for table creation, insertion, and CSV loading.

### Persistence

Table records and catalog metadata are persisted on disk.

After an insertion, the integration layer flushes the heap file and updates the catalog's page and tuple counts.

This allows records to remain available when the database engine is reopened.

## 4. Module 2 — Query Execution Engine

### Responsibilities

Module 2 executes physical query plans using iterator-based operators.

Its responsibilities include:

- Sequential scans
- Filtering
- Projection
- Sorting
- Duplicate elimination
- Grouping
- Set operations
- Join execution
- Operator-level instrumentation
- Memory-budget enforcement

### Iterator Model

Operators follow an iterator-based execution model:

```text
open()
next()
close()
```

Each operator consumes records from its child operators and produces records for its parent.

This allows physical query plans to be represented as trees of operators.

### Join Algorithms

The execution engine implements three join approaches:

1. Block nested-loop join
2. Hash join
3. Sort-merge join

The appropriate algorithm depends on input characteristics, memory availability, and the physical plan.

### Physical Plan Interface

Physical plans are represented as JSON-compatible dictionaries.

For example:

```json
{
  "op": "project",
  "columns": ["Employees.name"],
  "child": {
    "op": "seqscan",
    "table": "Employees"
  }
}
```

`PhysicalPlanExecutor` accepts a physical plan and returns:

- Output schema
- Result rows
- Execution counters
- Operator statistics

The execution counters include page reads, page writes, comparisons, and output tuple counts.

## 5. Module 3 — SQL Frontend

### Responsibilities

Module 3 converts SQL text into a validated logical representation.

Its processing stages include:

1. Lexical analysis
2. Parsing
3. Abstract syntax tree construction
4. Semantic validation
5. Logical-plan compilation

### Abstract Syntax Tree

SQL statements are represented using structured Python objects.

Examples include:

- `CreateTable`
- `Insert`
- `Select`
- `SetOperation`
- `Column`
- `Literal`
- `Comparison`

### Logical Plan Interface

The SQL compiler produces JSON-compatible logical plans.

These plans describe relational operations independently of the physical execution algorithms.

This separation allows the optimizer to transform logical plans before selecting executable operators.

### Semantic Validation

The SQL frontend uses catalog metadata to resolve tables and columns and validate query references.

The integration layer uses `SQLParser` and `SQLCompiler` rather than implementing another SQL parser.

## 6. Module 4 — Query Optimizer

### Responsibilities

Module 4 transforms logical query plans into more efficient executable plans.

Its responsibilities include:

- Collecting table statistics
- Estimating predicate selectivity
- Estimating intermediate cardinalities
- Applying logical rewrites
- Evaluating join orders
- Estimating physical execution costs
- Selecting physical join algorithms

### Statistics

`StatisticsStore` persists collected table statistics.

The optimizer uses table and column statistics to estimate the cost of alternative plans.

Statistics are collected through the `ANALYZE` command.

### Logical Rewrites

The optimizer supports transformations such as pushing eligible filters and projections toward scan operators.

These rewrites can reduce the amount of data processed by downstream operators.

### Join Ordering

The optimizer implements a dynamic-programming-based approach to join ordering.

The search is restricted to supported plan shapes rather than exhaustively enumerating every possible bushy join tree.

This reduces optimization complexity but may exclude a globally optimal plan.

### Physical Plan Lowering

`lower_physical_plan()` converts supported optimized logical operators into Module 2 physical-plan dictionaries.

This is the boundary between optimization and execution.

Not all SQL grammar features currently have corresponding physical lowering support.

## 7. Integration Layer

### Main Components

The integration layer consists of:

```text
dbshell
src/integration/
    __init__.py
    engine.py
    shell.py
```

### DatabaseEngine

`DatabaseEngine` coordinates:

- Database initialization
- Buffer-frame configuration
- Table creation
- Record insertion
- CSV loading
- Statistics collection
- SQL compilation
- Query optimization
- Physical execution
- Query result reporting

It uses existing module interfaces rather than duplicating their core implementations.

### Interactive Shell

The shell accepts semicolon-terminated statements and provides a persistent interactive session.

It supports:

```sql
CREATE TABLE ...
INSERT INTO ... VALUES ...
SELECT ...
LOAD table FROM 'file.csv';
ANALYZE table;
EXPLAIN SELECT ...;
EXPLAIN ANALYZE SELECT ...;
SET frames = 32;
```

The shell also supports `.quit` and `.exit`.

Statement buffering handles multiple complete statements and semicolons inside single-quoted strings.

### Error Handling

Invalid statements are reported to the user without automatically terminating the interactive session.

Unsupported physical-plan constructs raise explicit errors.

The integration layer does not silently substitute an incorrect physical operation for an unsupported query.

## 8. Module Interfaces

| Boundary | Input | Output |
|---|---|---|
| User → Integration | SQL text | Results or errors |
| Integration → M3 | SQL statement | AST and logical plan |
| M3 → M4 | Logical-plan dictionary | Optimized logical plan |
| M4 → M2 | Physical-plan dictionary | Executed result |
| M2 → M1 | Table and page requests | Stored records |
| M1 → M3/M4 | Catalog metadata | Schema and table information |
| Statistics → M4 | Collected statistics | Cardinality and cost inputs |

Using structured plans as intermediate representations allows modules to remain separately testable.

## 9. Memory Management

The database exposes a configurable frame budget.

For example:

```sql
SET frames = 16;
```

The frame budget is passed into query planning and physical execution.

The execution engine requires at least four frames.

The budget affects the costs and feasibility of memory-sensitive algorithms such as sorting and joining.

## 10. EXPLAIN and Instrumentation

The shell supports two explanation modes.

### EXPLAIN

Produces the selected physical plan and an estimated I/O cost without executing the query.

### EXPLAIN ANALYZE

Executes the query and reports:

- Query results
- Estimated page I/O
- Measured page I/O
- Execution counters

Estimated I/O and measured I/O are distinct metrics.

A difference between them may arise from estimation assumptions, physical operator behavior, and the actual number of page accesses.

The integration layer currently reports aggregate executor counters rather than a complete per-operator estimated-versus-actual cardinality tree.

## 11. Testing Strategy

Testing is organized at multiple levels.

### Unit Tests

Verify individual storage, parsing, execution, and optimization components.

### Module Integration Tests

Verify interactions between components within a module.

### Full-System Integration Tests

Verify SQL execution through the unified integration layer.

The integration tests cover:

- Table creation and insertion
- Persistent storage
- Projection and filtering
- CSV loading
- Statistics collection
- EXPLAIN and EXPLAIN ANALYZE
- Buffer-frame configuration
- Multiple statements
- Quoted semicolons
- Invalid input handling
- Unsupported queries
- Interactive shell execution
- Recovery after statement errors
- SQL sorting, DISTINCT, and LIMIT
- GROUP BY, aggregate functions, and HAVING
- UNION, UNION ALL, INTERSECT, and EXCEPT
- Set-operation schema compatibility
- Output column aliases
- Combined SQL operations

### Verified Results

On November 8, 2026:

- 1,576 automated tests passed.
- All 25 queries in the deterministic integration workload executed successfully.
- Table statistics were collected using ANALYZE before benchmarking.
- Ruff linting passed.
- Ruff formatting passed.

The benchmark records result counts, measured page I/O, estimated page I/O,
execution time, estimated root cardinality, actual root cardinality,
and cardinality q-error.

These measurements apply to the supported integration workload.
They do not establish correctness for all unpublished SQL queries.

## 12. Known Limitations

The integrated database is an educational implementation with several limitations.

### SQL Coverage

The SQL frontend accepts a broader language than the physical
lowering layer can execute.

The unified execution path now supports grouping, aggregate
functions, HAVING, sorting, duplicate elimination, limiting,
and the four SQL set operations.

Remaining limitations include unsupported complex expressions,
some Boolean predicates, restricted join conditions, and
incomplete support for certain alias and derived-table scenarios.

### Physical Lowering

Supported physical filters primarily use column-to-literal comparisons, including supported conjunctions.

Physical joins require supported equality predicates between columns belonging to opposite inputs.

Repeated table references and some complex expressions require additional alias or expression support.

### Query Optimization

The optimizer uses estimated statistics and a restricted plan search space.

Consequently, the selected plan is not guaranteed to be globally optimal.

### Transaction Processing

The integration layer does not implement a complete transactional SQL interface with commit, rollback, isolation, and crash recovery.

### Hidden Workload

Passing the existing tests does not establish correctness for all unpublished queries.

The final workload must be evaluated separately.

## 13. Retrospective — What We Would Do Differently

The modular design helped isolate failures and allowed individual components to be tested before integration.

However, integrating the modules exposed several architectural lessons.

### 13.1 Define Executable SQL Coverage Earlier

The SQL parser supports constructs that the physical lowering layer cannot yet execute.

If starting again, we would define a shared feature-support matrix before implementing the frontend and optimizer.

Each SQL feature would be tracked through parsing, semantic analysis, logical planning, physical lowering, and execution.

This would reduce the gap between syntactically valid SQL and executable SQL.

### 13.2 Add End-to-End Tests Earlier

Module-level tests establish that individual components work, but they cannot verify that the interfaces compose correctly.

If starting again, we would introduce a small end-to-end SQL query at the beginning of the project and expand it at every checkpoint.

This would expose interface mismatches earlier.

### 13.3 Standardize Result and Instrumentation Interfaces

The integration layer must interpret schemas, result rows, estimated costs, and execution counters returned by separate modules.

A shared, documented result interface would simplify reporting and make it easier to compare estimated and measured metrics.

### 13.4 Make Error Handling Consistent

Errors can originate in parsing, semantic analysis, optimization, storage, or execution.

A common database error hierarchy would make failures easier to classify and present consistently in the shell.

### 13.5 Improve Query Coverage Before Performance Tuning

Correctness is the primary objective of the final integration workload.

If starting again, we would prioritize complete execution of the required SQL subset before expanding optimizer sophistication.

This would provide a more reliable foundation for later performance improvements.

## 14. Conclusion

Future development priorities include broader SQL expression
support, validation against unpublished workloads, improved
estimated-versus-actual execution reporting, and more complete
transaction processing.