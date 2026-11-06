
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

The professor confirmed that the seven translation examples in Section 5
are the authoritative plan schema; no separate schema or sample catalog
will be supplied. Our catalog uses the existing Module 1 catalog format.

The examples define operator names and the canonical node hierarchy.
Where they do not define optional fields, we document local choices below.

The optional `aliases` mapping records renamed projection outputs; the
optional positional `outputs` list preserves repeated expressions with
different aliases. These fields are our documented extension because the
Section 5 examples do not show the JSON representation for projection
aliases. Both are omitted when no output names differ from source names.

`SELECT DISTINCT` emits `distinct` after a normal projection, but not
after `group_by`: grouping already returns one row per group, so the
extra elimination would be redundant. Aggregate-only queries are treated
as one implicit group, including on empty input.

For `ORDER BY` on a column absent from the select list, the current
compiler sorts before projection to keep the sort key accessible. This
is a documented exception to Section 5's canonical operator ordering;
it requires a design decision before claiming strict canonical-plan
compliance.

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

### CLI Error Handling

The SQL front end reports errors using the format:

`error: <category>: <message> at line L, column C`

The supported categories are lexical, syntax, name, ambiguity, type,
aggregate, and schema.

Lexical, syntax, and semantic errors use their available source
locations. Errors not associated with a SQL token, such as missing
database directories or catalog files, use line 1, column 1 as a
documented fallback.

The check command returns exit code 0 for success and 1 for failure.
The compile command follows the same convention.

CREATE TABLE and INSERT are supported by the parser but are not yet
supported by the semantic checker or logical-plan compiler. Those
commands currently report a categorized syntax error rather than
silently accepting unsupported operations.