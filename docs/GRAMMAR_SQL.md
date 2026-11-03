
# Module 3 — SQL Grammar

## 1. Overview

This document defines the supported SQL subset for the COMP 3005
Module 3 SQL front end.

The implementation uses a handwritten tokenizer and recursive-descent
parser. It does not use regular expressions, parser generators, or eval.

SQL keywords are case-insensitive. Identifiers are case-sensitive.

## 2. Lexical Rules

```ebnf
identifier  = (letter | "_"), {letter | digit | "_"} ;
integer     = ["+" | "-"], digit, {digit} ;
string      = "'", {non_quote_character | "''"}, "'" ;

letter      = "A" ... "Z" | "a" ... "z" ;
digit       = "0" ... "9" ;
```

Comments begin with `--` and continue until the end of the line.

Whitespace and comments separate tokens but are otherwise ignored.

Comparison operators use maximal munch:

`=`, `<>`, `<`, `<=`, `>`, `>=`

Every token records its source line and column.

## 3. Statement Grammar

```ebnf
program       = {statement, ";"}, [statement], EOF ;

statement     = create_table
              | insert
              | query ;

create_table  = "CREATE", "TABLE", identifier,
                "(", column_definition,
                {",", column_definition}, ")" ;

column_definition
              = identifier, column_type ;

column_type   = "INT"
              | "VARCHAR", "(", integer, ")" ;

insert        = "INSERT", "INTO", identifier,
                "VALUES", "(", literal,
                {",", literal}, ")" ;

literal       = integer | string ;
```

## 4. Query Grammar

```ebnf
query         = query_term, {set_operator, query_term} ;

query_term    = select_block
              | "(", query, ")" ;

set_operator  = "UNION", ["ALL"]
              | "INTERSECT"
              | "EXCEPT" ;

select_block  = "SELECT", ["DISTINCT"], select_list,
                "FROM", from_clause,
                ["WHERE", condition],
                ["GROUP", "BY", column_list,
                    ["HAVING", condition]],
                ["ORDER", "BY", sort_list],
                ["LIMIT", integer] ;

select_list   = "*"
              | select_item, {",", select_item} ;

select_item   = (column | aggregate), ["AS", identifier] ;

aggregate     = aggregate_name, "(",
                (column | "*"), ")" ;

aggregate_name
              = "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" ;

from_clause   = table_ref, {from_extension} ;

from_extension
              = ",", table_ref
              | "JOIN", table_ref, "ON", condition ;

table_ref     = identifier, ["AS", identifier]
              | identifier, identifier
              | "(", query, ")", "AS", identifier ;

column_list   = column, {",", column} ;

column        = identifier, [".", identifier] ;

sort_list     = sort_item, {",", sort_item} ;

sort_item     = column, ["ASC" | "DESC"] ;
```

## 5. Boolean Conditions

The grammar encodes precedence through separate nonterminals.

```ebnf
condition     = disjunction ;

disjunction   = conjunction, {"OR", conjunction} ;

conjunction   = negation, {"AND", negation} ;

negation      = "NOT", negation
              | "(", condition, ")"
              | comparison ;

comparison    = operand, comparison_operator, operand ;

comparison_operator
              = "=" | "<>" | "<" | "<="
              | ">" | ">=" ;

operand       = column | integer | string ;
```

## 6. Precedence and Associativity

| Operators | Precedence | Associativity |
|---|---|---|
| Parentheses | Highest | Explicit grouping |
| NOT | High | Right-associative |
| AND | Medium | Left-associative |
| OR | Low | Left-associative |
| UNION, UNION ALL, INTERSECT, EXCEPT | Equal | Left-associative |

Unlike standard SQL, this assignment gives all set operators
equal precedence and evaluates them from left to right.

## 7. Semantic Rules

The parser constructs syntax trees. Semantic analysis then:

1. Builds a scope for each FROM clause.
2. Resolves qualified and unqualified column references.
3. Expands SELECT * in FROM order and schema order.
4. Detects unknown tables, unknown columns, and ambiguous names.
5. Validates comparison operand types.
6. Validates aggregate usage and GROUP BY restrictions.
7. Validates positional compatibility for set operators.
8. Resolves ORDER BY aliases before FROM-scope columns.

Every resolved column in a logical plan is fully qualified.

## 8. Bag Semantics

SQL preserves duplicate rows by default.

- SELECT without DISTINCT preserves duplicates.
- SELECT DISTINCT adds duplicate elimination.
- UNION ALL preserves duplicates.
- UNION, INTERSECT, and EXCEPT use set semantics.
- GROUP BY inherently produces one row per group.

A redundant DISTINCT operator is not added above a grouping
operation when the selected output is already unique by group.

## 9. Canonical Logical Plan Order

For each SELECT block, logical operators are constructed
in this order, from bottom to top:

1. FROM: scan, rename, join, cross
2. WHERE: select
3. GROUP BY: group_by
4. HAVING: select
5. SELECT: project, optionally distinct
6. ORDER BY: sort
7. LIMIT: limit
8. Set operators combine complete query blocks

No predicate pushdown, join reordering, or physical algorithm
selection occurs in Module 3.

## 10. Supported Subset and Deviations

This is a restricted teaching SQL dialect, not full PostgreSQL.

Not supported unless explicitly extended:

- UPDATE, DELETE, ALTER TABLE, DROP TABLE
- LEFT, RIGHT, FULL, NATURAL joins
- Scalar or correlated subqueries in WHERE
- EXISTS, IN, BETWEEN, LIKE, IS NULL
- CASE, arithmetic expressions, concatenation
- COUNT(DISTINCT ...)
- NULL literals and three-valued logic
- OFFSET
- CREATE VIEW, triggers, indexes, transactions

Subqueries in FROM are supported and require an alias.

The exact serialized logical-plan field names must follow the
instructor-provided JSON schema.
