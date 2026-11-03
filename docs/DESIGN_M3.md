
# Module 3 — SQL Front End

## Overview

The SQL front end provides parsing, semantic validation, and
logical-plan compilation for the database system.

It integrates with the existing storage catalog to resolve table
names, column names, and data types.

The front end does not execute SQL queries or modify stored data.

## Architecture

SQL source
    |
    v
Tokenizer
    |
    v
Parser
    |
    v
Abstract Syntax Tree (AST)
    |
    v
Catalog / Name Resolution
    |
    v
Semantic and Type Validation
    |
    v
Logical Plan Compiler
    |
    v
JSON Logical Operator Tree

## Command-Line Interface

Run commands from the repository root using:

    python3 -m src.sql.cli

### Parse SQL

    python3 -m src.sql.cli parse \
      --query "SELECT * FROM BenchLeft;" \
      --explain

The --explain option displays the parsed AST as JSON.

SQL can also be loaded using --file.

### Validate SQL

    python3 -m src.sql.cli check \
      --db ./experiments/m2/results/join_costs_db/small \
      --query "SELECT id FROM BenchLeft WHERE id > 10;"

This validates SQL against an existing database catalog.

### Compile SQL

    python3 -m src.sql.cli compile \
      --db ./experiments/m2/results/join_costs_db/small \
      --query "SELECT id FROM BenchLeft ORDER BY id DESC LIMIT 5;" \
      --json

The compiler generates a logical operator tree in JSON.

## Supported SQL Features

- SELECT and SELECT DISTINCT
- Column references and SELECT *
- Table aliases
- WHERE conditions
- Boolean expressions
- CROSS JOIN and JOIN
- Derived tables
- GROUP BY and HAVING
- Aggregate functions
- ORDER BY and LIMIT
- UNION, UNION ALL, INTERSECT, and EXCEPT

CREATE TABLE and INSERT are represented in the AST but are not
handled by the check or compile commands.

## Logical Plan Operators

The compiler produces JSON-serializable plans using operators
including:

- scan
- rename
- select
- project
- cross
- join
- group_by
- distinct
- sort
- limit
- union
- union_all
- intersect
- except

Projection nodes may include an aliases mapping that associates
output names with source expressions.

The JSON structure is the project's current internal logical-plan
representation and has not yet been verified against an external
assignment-specific schema.

## CLI Exit Codes

- 0: Success
- 1: SQL parsing, validation, or compilation error
- 2: Invalid input path or command-line usage

Diagnostics are written to stderr.

## Testing

Run the SQL tests:

    python3 -m pytest tests/test_sql_*.py -q

Run the full regression suite:

    python3 -m pytest tests/ -q

Run Ruff:

    python3 -m ruff check src/sql/ tests/test_sql_*.py
    python3 -m ruff format --check src/sql/ tests/test_sql_*.py

## Limitations

- The SQL CLI does not execute logical plans.
- CREATE TABLE and INSERT execution are outside the current CLI.
- The compiler uses a project-specific JSON plan representation.
- Query optimization and physical execution planning are separate
  concerns.
