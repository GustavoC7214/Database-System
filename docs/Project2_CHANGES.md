# Project 2 — Changes from Project 1

## Architecture

- Separated the lexer, parser, AST, and evaluator into reusable modules.
- Added standalone condition parsing and evaluation.
- Added JSON serialization and deserialization for AST nodes.
- Introduced a TupleProvider interface to decouple relational
  operators from in-memory database storage.
- Preserved support for qualified attribute references.

## Bag Semantics

Project 2 preserves duplicate tuples by default.

- Relation construction no longer automatically removes duplicates.
- Projection preserves duplicate rows.
- UNION concatenates both inputs, preserving multiplicities.
- INTERSECT retains the minimum multiplicity of matching rows.
- MINUS subtracts right-side multiplicities from left-side
  multiplicities, with a minimum result of zero.
- DISTINCT explicitly removes duplicate rows.

## Testing

- Updated Project 1 tests where expected results depended on
  automatic duplicate removal.
- Added regression tests for bag semantics, condition evaluation,
  tuple providers, and AST serialization.
- Added end-to-end tests for DISTINCT.

Week 1 baseline: 249 passing tests.