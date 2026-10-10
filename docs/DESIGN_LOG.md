# Design Log

## September 14, 2026 — Relational Algebra Preparation

### Goal

Before beginning the relational algebra query processor, I wanted to make sure I understood the relational algebra operations that the engine will need to support.

### What I Did

I practiced writing relational algebra queries using selection (`σ`), projection (`π`), joins (`⋈`), union (`∪`), intersection (`∩`), difference (`−`), and rename (`ρ`). I also practiced nested expressions, self-joins, Boolean conditions using `and`, `or`, and `not`, and comparisons involving dates.

I worked through queries involving multiple conditions and learned how parentheses and Boolean operators affect the meaning of selection conditions. I also practiced using rename when two relations need compatible attribute names for set operations and when a relation needs to participate in a self-join.

### What I Learned

The order and grouping of operations are important because changing the structure of a relational algebra expression can change its result. I also learned that schemas matter for operations such as union, intersection, difference, joins, and self-joins.

This preparation gave me a better understanding of the operations that the query processor will eventually need to represent, parse, and execute.

### Problems / AI Assistance

During practice, AI feedback helped identify mistakes in some of my relational algebra expressions, especially Boolean conditions involving `not`, `and`, and `or`. This showed me that expressions that look similar can have different meanings depending on their grouping. I verified corrections by working through the conditions and determining which tuples should satisfy them rather than relying only on the suggested answer.

## September 15, 2026 — Grammar Design

### Goal

My goal was to define the complete EBNF grammar for the relational algebra language before beginning the tokenizer or parser. I also needed to decide operator precedence and associativity, demonstrate ambiguity in a naive grammar, and choose a parsing strategy.

### What I Did

I defined lexical rules for identifiers, numbers, quoted strings, bare strings, and relation definitions. I then created grammar rules for `select`, `project`, `rename`, `union`, `intersect`, `minus`, `times`, and theta joins.

I separated relational expressions into precedence levels using `SET_EXPR`, `PRODUCT_EXPR`, and `PRIMARY_EXPR`. I also separated conditions into `OR_CONDITION`, `AND_CONDITION`, `NOT_CONDITION`, and `COMPARISON` so that comparisons bind tighter than `not`, which binds tighter than `and`, which binds tighter than `or`.

I chose left associativity for `union`, `intersect`, `minus`, `times`, and `join`, and right associativity for repeated `not`. I also chose recursive descent as the parsing strategy and structured the grammar to avoid left recursion.

For `project[Name, Name](R)`, I decided that the expression is syntactically valid but will produce a semantic error because duplicate attributes are not allowed in a projection list.

### What I Learned

I learned that ambiguity and associativity have to be decided by the grammar rather than handled as special cases in the parser. For example, my grammar makes:

`A union B minus C`

group as:

`(A union B) minus C`

and:

`A minus B minus C`

group as:

`(A minus B) minus C`.

I also learned why a directly left-recursive rule such as:

`Expr ::= Expr "union" Expr`

does not work with a recursive-descent parser. The parser could recursively call itself without consuming any input. Using EBNF repetition after first parsing an operand avoids this problem and also provides a natural way to construct left-associative expressions.

### Problems / AI Assistance

There were three specific cases where AI assistance was incorrect or incomplete during the grammar design.

1. While creating the ambiguity demonstration, AI initially suggested `A = {1}`, `B = {2}`, and `C = {2}` for `A union B minus C`. I manually evaluated both parse trees and found that they both produced `{1}`, so the example did not actually demonstrate ambiguity affecting the result. I changed `C` to `{1}`, which makes `(A union B) minus C = {2}` while `A union (B minus C) = {1, 2}`.

2. An earlier AI-assisted version of the grammar only allowed `NUMBER` and quoted `STRING` values in relation definitions. Comparing this with the assignment examples showed that values such as `E1`, `John`, and `D1` also need to work without quotes. I corrected this by adding a `BARE_STRING` token and allowing it in `RELATION_VALUE`.

3. AI initially suggested constructing `BARE_STRING` using `LETTER` and `NUMBER`. I noticed that this was incorrect because `NUMBER` represents a complete numeric token such as `42` or `-7`, not a single character. I corrected the grammar by defining `BARE_STRING_CHAR` separately and then defining `BARE_STRING` as one or more of those characters.

## September 16/17, 2026 — Tokenizer Implementation and Testing

### Goal

Implement the tokenizer based on the lexical rules defined in `GRAMMAR.md` and verify that it correctly converts the input language into tokens before beginning the parser.

### What I Did

I implemented a hand-written tokenizer that scans the source character by character without using regular expressions or parser-generation libraries. The tokenizer tracks the index, line, and column of each token so lexical errors can report their source position.

I added support for identifiers, numbers, quoted strings, bare strings, punctuation, comparison operators, comments, and significant newlines inside relation definitions. Comparison operators use maximal munch so operators such as `>=`, `<=`, and `!=` are emitted as single tokens, while an expression such as `Age>-30` produces `>` and `-30` separately.

Keywords such as `select`, `union`, and `and` are tokenized as identifiers. Their meaning will be determined later by the parser based on context. This also allows a keyword to be used as an attribute name where the grammar permits it.

Relation data required additional tokenizer state because newlines are significant between tuples but normally ignored elsewhere. I used `inside_relation_data` and `line_has_data` to distinguish tuple-ending newlines from blank or comment-only lines.

### What I Learned

The tokenizer should only determine whether the source characters can be converted into valid tokens. It should not decide whether those tokens form a grammatically valid expression. For example, `select[Age=](R)` can be tokenized successfully, but the parser must later reject it because the comparison is missing its right operand.

I also learned that tokenization rules sometimes depend on context. Inside relation data, an unquoted value must be scanned completely before it is classified. For example, `123abc` must become one `BARE_STRING` rather than `NUMBER("123")` followed by another token.

The tokenizer must also follow the lexical grammar exactly. Python methods such as `isalpha()` and `isdigit()` accept Unicode characters, while my grammar defines letters and digits as ASCII `A-Z`, `a-z`, and `0-9`. I therefore implemented explicit ASCII checks.

### Problems / AI Assistance

During implementation, AI initially suggested logic for detecting `//` comments while scanning a bare relation value that used the wrong lookahead position. Testing `D1//comment` exposed the problem because the comment marker was being consumed as part of the bare string. I corrected this by checking the two characters beginning at the tokenizer's current position before continuing to scan the value.

Another issue appeared with a relation containing a tuple made entirely from a quoted string. The tokenizer initially failed to emit the tuple's terminating `NEWLINE` because scanning a string did not mark the line as containing relation data. I fixed this by setting `line_has_data` after a string is successfully scanned inside relation data and added a regression test for the case.

The initial implementation also used Python's `isalpha()`, `isalnum()`, and `isdigit()` methods. Comparing this implementation against my grammar showed that these methods accept characters outside the grammar's ASCII definition. I replaced them with explicit ASCII letter and digit checks and verified the change with a non-ASCII identifier test.

### Testing

I implemented all nine required tokenizer tests from the project specification. These cover whitespace handling, maximal-munch comparison operators, negative numbers, punctuation inside quoted strings, commas inside strings, doubled quotes, keywords used as attributes, and unterminated strings with source positions.

I also added regression tests for issues discovered during development, including alphanumeric bare relation values, quoted-only tuples, comment-only lines, inline comments without whitespace, non-ASCII identifiers, identifiers beginning with an underscore, and standalone `!`.

At the end of this session, the tokenizer test suite contained 16 tests and all 16 passed.

## September 17/18, 2026 — Parser Completion and Query Tree Printer

### Parser Completion

Finished testing the recursive-descent parser against the required grammar and precedence cases.

Additional parser tests were added for:
- Left-associative set operations.
- Parentheses overriding relational operator precedence.
- `not`, `and`, and `or` condition precedence.
- Nested `select` and `project` expressions.
- Missing closing parentheses and empty projection attribute lists.
- Rejection of trailing tokens.
- Non-associative comparison operators.

The parser test suite reached 29 passing tests.

### Query Tree Printer Design

Implemented a query tree printer in `src/parser/tree_printer.py`.

The printer operates directly on the AST and does not execute the query. I separated the printer into several responsibilities:

- `print_tree()` handles the root node and produces the final multiline string.
- `print_node()` recursively prints child expression nodes and manages tree branches and indentation.
- `format_expression()` creates labels for relational expression nodes.
- `format_inline()` formats conditions and operands that are displayed inside expression labels.
- `get_children()` determines which expression nodes should appear as branches.
- `format_attribute_name()` formats qualified and unqualified attribute names.

Conditions are displayed inline rather than as separate tree branches. This follows the tree format shown in the assignment. For example:

    Project(attrs=[Name])
    └── Select(cond=Gt(Attr(Age), Num(30)))
        └── Relation(Employees)

Binary expressions use `├──` and `└──` branches. The prefix is extended with `│   ` when additional siblings remain and four spaces when the current node is the final child.

The printer supports:
- Relation references
- Select
- Project
- Rename
- Union
- Intersect
- Minus
- Times
- Join
- Comparisons
- Boolean `and`, `or`, and `not`
- Qualified and unqualified attributes
- Number and string literals

Unsupported AST node types explicitly raise `TypeError` rather than implicitly returning `None`.

### Tree Printer Testing

Added `tests/test_tree_printer.py` with tests for:
- Nested `Project -> Select -> Relation`
- Nested binary expressions and branch indentation
- Complex `not` / `and` / `or` conditions
- Join conditions with qualified attributes
- Rename
- Cartesian product (`times`)

All 6 tree-printer tests passed.

After completing the tree printer, the complete test suite was run:

    51 passed

Ruff was also installed in the project virtual environment and run across the project:

    python3 -m ruff check .

Result:

    All checks passed!

### Design Decisions / Issues Encountered

- Initially considered treating conditions as separate tree branches, but kept them inline because this matches the query-tree format required by the assignment.
- The root node is handled separately by `print_tree()` because using an empty prefix alone cannot reliably distinguish the root from its first child.
- `format_inline()` is kept separate from `format_expression()` so condition formatting cannot accidentally introduce tree branch characters.
- Used `list.extend()` instead of `append()` when combining recursively generated tree lines.
- Fixed an infinite-recursion bug in `Not` formatting by recursively formatting `node.condition` instead of the `Not` node itself.
- Used `isinstance(node, (Select, Project, Rename))` for multiple-type checks instead of `isinstance(node, Select or Project)`.
- Qualified projection attributes preserve their relation name, for example `Member.Name`.

## September 19/20, 2026 — Relational Algebra Evaluator Implementation and Testing

### Goal

Implement and test the relational algebra evaluator so that it can execute AST expressions produced by the parser and return the resulting relations.

### What I Did

I implemented the evaluator in `src/engine/evaluator.py`. The evaluator recursively processes AST nodes and uses the database to retrieve relations referenced in queries.

I implemented support for the following relational algebra operations:

- Selection (`select`): Filters rows based on a condition.
- Projection (`project`): Selects specific attributes from a relation.
- Sorting (`sort`): Orders rows by an attribute in ascending or descending order.
- Cartesian product (`times`): Combines every row from the left relation with every row from the right relation.
- Theta join (`join`): Combines rows from two relations when they satisfy a specified condition.
- Union (`union`): Combines rows from two compatible relations and removes duplicates.
- Intersection (`intersect`): Returns distinct rows that appear in both relations.
- Difference (`minus`): Returns distinct rows that appear in the left relation but not in the right relation.
- Rename (`rename`): Creates a relation with a new relation name while preserving its rows and attributes.

I also implemented condition evaluation for comparison operators (`=`, `!=`, `<`, `<=`, `>`, `>=`) and Boolean operators (`and`, `or`, `not`).

Attribute references can be qualified with a relation name or left unqualified. The evaluator checks for undefined and ambiguous attribute references.

### Design Decisions

I used recursive evaluation so that operators can be nested. For example, the evaluator can execute a selection whose input is a join between two renamed copies of the same relation.

Each operation returns a `Relation` object rather than modifying the original relations stored in the database.

For union, intersection, and difference, I check that the input relations have the same number of attributes and compatible column data types. The current type check compares the first row of each relation when both relations contain rows.

I remove duplicate rows from the results of union, intersection, and difference.

For rename, I extended the existing `Rename` AST class with an optional `attribute_renames` dictionary. The evaluator updates the relation name and attribute metadata while preserving the original row values.

### Problems / AI Assistance

AI assistance helped me work through the evaluator implementation using questions about each operation before writing the complete code.

While implementing rename, I identified a mismatch between the existing AST field name, `new_name`, and the suggested evaluator code, which used `new_relation_name`. I corrected the evaluator to use `expression.new_name`.

I also added the missing `Attribute` import required to construct renamed attributes.

After completing the individual operators, I tested nested expressions involving rename, theta join, and selection to verify that the operations work together.

### Testing

I added tests in `tests/test_evaluator.py` to verify the behavior of the relational algebra operators and condition evaluation.

The tests cover normal results, empty relations, duplicate rows, incompatible schemas, and attribute resolution.

I also added tests for self-joins using two renamed copies of the same relation. One test verifies that the join correctly uses qualified attributes, while another combines the self-join with selection to exclude self-pairs and reversed duplicates.

After completing the evaluator and the nested-expression tests, I ran:

    python -m pytest tests/test_evaluator.py -q

Result:

    76 passed in 0.07s

### Next Steps

Connect the existing tokenizer and recursive-descent parser to the evaluator so that users can enter relational algebra queries as text, generate the corresponding AST, and execute the queries against the database.

## September 20/21, 2026 — Query Processor Integration and Command-Line Interface

### Goal

Connect the tokenizer, parser, database, and evaluator into a complete query-processing pipeline and provide a simple command-line entry point for loading relations, executing queries, and printing parse trees.

### What I Did

I implemented `QueryProcessor` in `src/engine/query_processor.py`. The query processor accepts source text, tokenizes it, parses it into an AST, and then either stores a relation definition in the database or sends a relational expression to the evaluator.

This created the complete processing pipeline:

`source text → tokenizer → parser → AST → evaluator → Relation`

Relation definitions are converted from their parsed `RelationDefinition` nodes into `Relation`, `Attribute`, and `Row` objects before being added to the database.

I added integration tests in `tests/test_query_processor.py` to verify that the complete pipeline works rather than testing each component only in isolation.

During integration testing, I corrected the compatibility checks for `union`, `intersect`, and `minus`. The two input relations must have the same number of attributes, the same attribute names in the same order, and compatible column types.

A shared compatibility-checking helper is used by all three set operations so that the rules are implemented consistently.

### Command-Line Interface

I added `ra.py` at the project root as the command-line entry point.

Normal query execution uses a relation-definition file and a query:

`python ra.py --file tests/relations.ra "project[Name, Age](select[Age>25](Member))"`

The relation file is loaded into a `Database`, after which the query is processed through `QueryProcessor`.

Query results are displayed using a simple table formatter implemented with standard Python rather than an external table-formatting dependency.

Empty results still display their schema followed by `(no rows)`.

I also added parse-tree mode:

`python ra.py --tree "project[Name](select[Age>25](Member))"`

Tree mode tokenizes and parses the expression and prints its AST without evaluating it or requiring a relation file.

### Error Handling

The command-line interface catches expected language and file errors so users do not receive Python stack traces.

Errors are displayed using categories including:

- `Lexical Error`
- `Syntax Error`
- `Name Error`
- `Schema Error`
- `Type Error`
- `File Error`
- `Usage Error`

This keeps lexical, parsing, semantic, and command-line failures distinguishable to the user.

### Design Decisions

I kept `ra.py` at the project root so the program can be executed directly using `python ra.py`.

I chose a file-based approach for relation definitions instead of building an interactive shell. This keeps the command-line interface small while still allowing multiple relations to be loaded before executing a query.

The CLI uses only the Python standard library. Table formatting is implemented directly rather than adding an external dependency.

In `--tree` mode, relation files are not loaded because printing the parse tree only requires tokenization and parsing.

Successful relation loading does not produce additional output. Only the result of the requested query is displayed.

### Problems / AI Assistance

AI assistance was used to review the integration design and identify test cases, but the behavior was verified through automated tests and manual command-line execution.

During set-operation integration testing, I found that earlier evaluator tests allowed relations with different attribute names to participate in set operations. Comparing this behavior with the project specification showed that this was incorrect. I updated the compatibility check and the affected tests so that attribute names and order must match.

A type-checking limitation remains in the current set-operation compatibility implementation: column types are compared using the first row of each relation when both relations contain rows. If either relation is empty, there is no row value available from which to infer that column's type.

### Testing

I added command-line tests in `tests/test_cli.py` covering:

- Normal query execution
- Parse-tree mode
- Tree mode without a relation file
- Empty query results
- Undefined attributes and relations
- Lexical errors
- Syntax errors
- Type errors
- Missing relation files
- Missing `--file`
- Silent relation loading
- Prevention of Python tracebacks

The CLI test suite contains 14 tests, all of which pass.

After completing the query processor and command-line interface, I ran the complete test suite:

`python -m pytest tests/ -q`

Result:

`176 passed in 0.77s`

## September 21, 2026 — Sorting Syntax, Parser, and Tree Printer Integration

### Goal

Expose the existing sorting functionality through the relational algebra language so that sorting can be written as part of a query, parsed into the AST, displayed in a query tree, and executed through the command-line interface.

### What I Did

I extended the grammar with a sorting expression using the syntax:

`sort[ATTRIBUTE asc](EXPR)`

or:

`sort[ATTRIBUTE desc](EXPR)`

Sorting is treated as a unary relational operation at the same precedence level as `select`, `project`, and `rename`.

The AST already contained a `Sort` node and `SortDictionary` enum because sorting had previously been implemented in the evaluator. I updated the recursive-descent parser so that `sort` expressions can now be constructed directly from source text.

The parser reads the attribute to sort by, followed by either `asc` or `desc`. It also supports qualified attributes such as:

`sort[Member.Age desc](Member)`

The expression inside the parentheses is parsed recursively, allowing sorting to be combined with other relational operations. For example:

`sort[Age desc](select[Place='Ottawa'](Member))`

I also updated the query tree printer to recognize `Sort` nodes. A sort expression is displayed as a unary tree node containing the attribute and direction. For example:

    Sort(attr=Age, direction=desc)
    └── Relation(Member)

### Parser Testing

I added parser tests covering:

- Ascending sorting
- Descending sorting
- Qualified sort attributes
- Sorting a nested relational expression
- Rejection of invalid sort directions

After adding the sorting tests, the parser test suite contained 34 tests:

`python -m pytest tests/test_parser.py -q`

Result:

`34 passed in 0.06s`

### Tree Printer Testing

I added tree-printer tests covering:

- A basic sort expression
- Sorting using a qualified attribute
- A sort containing a nested selection

After these additions, the tree-printer test suite contained 9 tests:

`python -m pytest tests/test_tree_printer.py -q`

Result:

`9 passed in 0.01s`

### Command-Line Verification

I manually verified ascending sorting through the complete command-line pipeline:

`python ra.py --file tests/relations.ra "sort[Age asc](Member)"`

This returned the members in ascending age order:

`Alice (25), Bob (30), Charlie (35)`

I also verified descending sorting:

`python ra.py --file tests/relations.ra "sort[Age desc](Member)"`

This returned:

`Charlie (35), Bob (30), Alice (25)`

Finally, I verified parse-tree mode:

`python ra.py --tree "sort[Age desc](Member)"`

which produced:

    Sort(attr=Age, direction=desc)
    └── Relation(Member)

This confirmed that sorting now works through the complete pipeline:

`source text → tokenizer → parser → AST → evaluator → Relation`

and through the AST tree printer without evaluation.

### Problems / AI Assistance

AI assistance was used to review the changes needed to expose the existing sorting functionality through the parser and tree printer.

During parser integration, I initially used `TokenType.LBRACE` when checking whether `sort` was followed by its argument list. Testing and code review identified that the sorting syntax uses `[` rather than `{`, so I corrected the check to `TokenType.LBRACKET`.

I then verified the implementation with focused parser and tree-printer tests before running the complete regression suite.

### Regression Testing

After completing the sorting integration, I ran the complete test suite:

`python -m pytest tests/ -q`

Result:

`184 passed in 0.72s`

All existing tests continued to pass, confirming that adding sorting syntax did not introduce regressions in the tokenizer, parser, evaluator, query processor, tree printer, or command-line interface.

## September 21, 2026 — Data Generation and Performance Evaluation

### Goal

Create reproducible benchmark inputs, measure the performance of join, selection, and projection, and document how input size and join match rate affect execution time.

### What I Did

I implemented `data_generator.py` to generate relations `R(a, b)` and `S(b, c)` with configurable input sizes and match rates. I added tests to check the generated relation sizes and expected join output sizes.

I implemented `performance_runner.py` to execute benchmark queries and record wall-clock time using `time.perf_counter()`. The join benchmark also records tuple-pair comparisons, while the selection benchmark records input tuples examined. Data generation and relation loading occur before the query timer starts.

I ran join, selection, and projection experiments at input sizes of 1,000, 2,000, 4,000, 8,000, 16,000, 32,000, and 64,000 tuples. I also ran joins with fixed input sizes of 1,000 tuples and match rates of 1, 2, 4, and 8.

I saved the measurements in separate CSV files, calculated the join's log-log scaling slope, generated a log-log plot, and documented the results in `docs/REPORT.md`.

### Results and Design Observations

The join performed exactly `n × m` tuple-pair comparisons in every experiment. With `n = m = 64,000`, it performed 4,096,000,000 comparisons and took 5,566.992 seconds.

The measured join log-log slope was 1.9976, consistent with approximately quadratic growth when both input sizes increase together. Extrapolating from the largest measured run gives an estimated 15.63 days for a join with two one-million-tuple inputs. This estimate was not measured directly.

Selection examined exactly `n` input tuples, but both selection and projection showed approximately quadratic wall-time growth over the tested sizes. Result-relation construction and duplicate checking are likely contributors to this difference between the operation counters and total execution time.

When the join input sizes were fixed at 1,000 tuples each, increasing the match rate from 1 to 8 kept the comparison count at 1,000,000 but increased the output size from 1,000 to 8,000 tuples. Wall time increased as more output tuples were produced.

### Problems / AI Assistance

AI assistance helped organize the benchmark runner, CSV output, scaling calculation, plot, and report. I checked the benchmark results against the expected comparison counts and output sizes.

During report preparation, I distinguished measured execution times from the extrapolated million-tuple estimate. I also documented the difference between selection's linear tuple-examination count and the approximately quadratic wall time observed in the current implementation.