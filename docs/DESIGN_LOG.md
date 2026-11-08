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

## October 9th 2026 - October 20th 2026  — Project 2, Module 1: Storage Engine and Buffer Pool

### Goal

Implement a disk-based storage engine with fixed-size pages, slotted-page record storage, heap-file directories, buffer management, table metadata, CSV loading, and command-line operations.

### What I Did

I implemented the storage engine in `src/storage/`, including:

- DiskManager for reading, writing, and allocating 4096-byte pages.
- SlottedPage for storing variable-length records and managing record slots.
- DirectoryPage for tracking heap-file data pages and available space.
- HeapFile for inserting, retrieving, deleting, and scanning records.
- BufferPool with configurable LRU and CLOCK replacement policies.
- Record encoding and decoding for INT and VARCHAR fields.
- Schema parsing, catalog metadata, and CSV loading.
- Storage CLI commands for table creation, loading, scanning, layout inspection, and trace execution.

### Design Decisions

I used 4096-byte pages with little-endian binary layouts.

Records are stored in slotted pages. Each slot occupies four bytes and records grow backward from the end of the page.

Deleted slots are marked as dead and are not reused. Deleted record space is not reclaimed.

Heap files use directory pages to track data-page IDs and available space. The insertion algorithm uses first-fit placement.

The buffer pool tracks page pins, dirty pages, cache hits, misses, evictions, disk reads, and disk writes.

I implemented both LRU and CLOCK replacement policies to compare their behaviour under different workloads.

### Problems / AI Assistance

AI assistance was used to review the storage modules, identify edge cases, develop regression tests, and organize the experimental benchmarks.

During testing, I corrected several issues:

- Oversized records now produce explicit validation errors.
- Directory entries reject invalid free-space values.
- Heap-file record access validates that the requested page belongs to the heap.
- Invalid buffer-pool page requests no longer modify CLOCK replacement state.
- Malformed CSV input produces a descriptive error.
- The layout command rejects directory pages when a data page is required.

I verified the corrections using focused tests and the complete regression suite.

### Testing

After completing the implementation and regression review, I ran:

`python3 -m pytest -q`

Result: 485 tests passed.

I also ran:

`python3 -m ruff check .`

Result: All checks passed.

### Experiments

I measured theoretical and actual slotted-page capacities for three record schemas. All three matched:

- INT record: 511 records per page.
- Mixed INT/VARCHAR record: 240 records per page.
- Large VARCHAR record: 37 records per page.

I compared LRU and CLOCK using five access traces and buffer sizes of 4, 16, 64, and 256 frames, completing 40 benchmark runs.

LRU performed slightly better on the hot-set trace with 16 frames, while CLOCK performed slightly better on the random trace with 16 and 64 frames.

I also scanned a heap containing 500 data pages using buffer sizes of 2, 8, and 64 frames. Both replacement policies produced 500 disk reads for every scan. Increasing the buffer size reduced evictions but did not reduce reads.

The benchmark results are saved in:

- `experiments/m1/results/buffer_benchmarks.csv`
- `experiments/m1/results/sequential_scan.csv`

## October 20th 2026 - October 28th 2026 — Project 2, Module 2: Execution Engine

### Goal

Implement a disk-backed relational execution engine that consumes physical plans in JSON format, executes them through a common iterator interface, and respects a configurable shared memory budget.

### What I Did

I implemented the execution engine in `src/execution/`, including:

- The iterator interface with `open()`, `next()`, `close()`, and `counters()`.
- Sequential scanning, filtering, projection, and limiting.
- External merge sorting using disk-backed temporary runs.
- Sort-based and hash-based duplicate elimination and grouping.
- Block Nested Loop Join, Sort Merge Join, and Grace Hash Join.
- Set operations, including union, intersection, and difference.
- Physical-plan validation, operator construction, and execution.
- A shared page manager for buffer reservations and temporary-page I/O.
- Command-line support for executing and tracing physical plans.

### Design Decisions

I used a pull-based iterator model so operators request tuples from their children rather than materializing every intermediate result.

Blocking operations use temporary files when their working data exceeds the available memory.

External Merge Sort generates sorted runs and merges them using a bounded number of input buffers.

Block Nested Loop Join processes the outer relation in blocks and repeatedly scans the inner relation.

Sort Merge Join handles duplicate join keys, including groups that cannot fit entirely in memory.

Grace Hash Join partitions both relations before probing. If a build-side partition exceeds the available memory, the implementation falls back to a disk-backed nested-loop approach.

The shared page manager tracks reserved, cached, and pinned frames to help enforce the configured buffer budget.

### Problems / AI Assistance

AI assistance was used to review the execution-engine architecture, develop regression tests, interpret experimental results, and organize the reports.

**1. CSV benchmark-output regression**

During changes to the hash-skew experiment's CSV output, an earlier suggested modification changed the CSV writer configuration but accidentally omitted the calls responsible for writing the header and data rows.

I detected this problem through static analysis with Ruff, which identified unused variables. I inspected the affected code, restored the missing writer calls, and reran the experiment to verify that the expected CSV results were generated.

This demonstrated why even small AI-assisted changes to experimental code require validation.

**2. Predicted versus measured hash-partition overflow**

An earlier version of the skew experiment calculated partition-overflow counts from the partitioning function and memory-limit formula rather than recording actual overflow events during execution.

Reviewing the experiment against the assignment requirements revealed that predicted values alone did not adequately demonstrate what the implementation actually did.

I added runtime instrumentation to Grace Hash Join to record partition sizes and overflow-fallback events. I then updated the experiment to compare the predicted counts against the observed counts.

The predicted and observed overflow counts agreed across all eight tested configurations.

This improved the reliability of the experimental evidence and distinguished theoretical expectations from observed execution behaviour.

### Testing

The complete automated test suite passed:

`python3 -m pytest -q`

Result: 733 tests passed.

Static analysis and formatting checks also passed:

`python3 -m ruff check .`

`python3 -m ruff format --check .`

### Experiments

I completed five required experiments:

1. **Join costs:** Compared measured page I/O for the three join algorithms across four buffer budgets and three relation sizes.
2. **External sorting:** Compared theoretical and observed initial-run counts, merge passes, and page I/O.
3. **Join crossover:** Measured how join-algorithm performance changed with memory availability and relation size, generating comparison plots.
4. **Hash skew:** Compared uniform and skewed join-key distributions, recording actual partition sizes, overflow events, output cardinalities, and I/O costs.
5. **Memory stress:** Successfully sorted an 80-page relation with a four-frame shared buffer budget, confirming that no reserved or pinned frames remained after execution.

The experiment scripts and results are stored in `experiments/m2/`.

### Results and Design Observations

Grace Hash Join performed well when partitions fit within the available memory, but partition overflow caused substantial additional I/O.

External sorting required more initial runs than predicted by the idealized textbook formula in some configurations because the implementation's actual buffer allocation and temporary-page packing differed from the theoretical model.

The memory stress test completed successfully with a maximum observed shared-frame occupancy of four frames.

The implementation and experiments were committed as `78741d9` and pushed to the repository's `develop` branch.

## October 29th - November 5th 2026 — Project 2, Module 3: SQL Front End

### Goal

Implement a SQL front end that accepts the supported SQL language, converts statements into an abstract syntax tree, validates queries against the existing database catalog, and produces logical query plans in JSON format.

The implementation needed to reuse the Module 1 catalog and provide logical operator trees that could be consumed by later query optimization and execution components.

### What I Did

I implemented the SQL front end in `src/sql/`, including:

- A handwritten tokenizer that recognizes SQL keywords, identifiers, integer and string literals, comparison operators, punctuation, whitespace, and comments.
- A recursive-descent parser that constructs immutable SQL abstract syntax trees.
- AST representations for SELECT queries, joins, derived tables, aggregate expressions, set operations, CREATE TABLE, and INSERT statements.
- A read-only schema adapter over the existing Module 1 catalog.
- Semantic analysis for table names, column names, aliases, types, aggregation, grouping, and query output schemas.
- A logical-plan compiler that produces JSON-serializable operator trees.
- Command-line operations for parsing, semantic checking, and logical-plan compilation.

The SQL front end supports the following query constructs:

- SELECT and SELECT DISTINCT.
- WHERE conditions with AND, OR, and NOT.
- Qualified and unqualified column references.
- Table aliases, explicit joins, and cross products.
- Derived tables.
- GROUP BY and HAVING.
- COUNT, SUM, AVG, MIN, and MAX.
- ORDER BY with ASC and DESC.
- LIMIT.
- UNION, UNION ALL, INTERSECT, and EXCEPT.

The parser also recognizes CREATE TABLE and INSERT statements, although the semantic-checking and logical-compilation commands are restricted to query statements.

### Design Decisions

**1. Separate tokenization, parsing, semantic analysis, and compilation**

I divided the SQL front end into independent processing stages:

`SQL text -> tokens -> AST -> semantic analysis -> logical plan`

This allows lexical, syntax, name-resolution, type, and compilation problems to be tested separately.

The tokenizer and parser do not access the database catalog. Catalog-dependent validation happens during semantic analysis.

**2. Use a handwritten tokenizer and recursive-descent parser**

I implemented tokenization without regular expressions or parser generators.

The tokenizer tracks line and column positions so errors can identify the location of invalid input.

The recursive-descent parser uses separate methods for SQL statements, query expressions, table references, aggregates, and Boolean conditions.

Boolean expressions follow the precedence:

`NOT > AND > OR`

The parser also constructs left-associative set-operation trees and supports parentheses to override grouping.

**3. Represent SQL using immutable AST nodes**

I used frozen dataclasses with slots to represent SQL syntax.

Separate AST nodes represent columns, literals, aggregates, comparisons, logical conditions, table references, SELECT queries, and set operations.

This keeps parsing separate from semantic interpretation and prevents later stages from accidentally modifying the parsed query structure.

**4. Reuse the Module 1 catalog**

I implemented `SchemaCatalog` as a read-only adapter over the existing persistent catalog.

The adapter provides ordered table schemas and declared column types without changing the storage engine's catalog format.

Semantic analysis uses this metadata to validate table and column references.

**5. Resolve names before compiling logical plans**

The semantic analyzer builds a scope containing the tables and aliases available to each query.

Qualified references are resolved against their specified table or alias.

Unqualified references must match exactly one column in the current scope.

Unknown tables, unknown columns, duplicate table aliases, and ambiguous column references produce explicit errors.

Derived-table output columns are also validated before being added to the enclosing query scope.

**6. Validate SQL types and aggregate usage**

The semantic analyzer checks comparison operand compatibility and validates aggregate arguments.

COUNT returns an integer result, while SUM and AVG require integer arguments in the supported SQL subset.

MIN and MAX preserve the argument's declared type.

For grouped queries, selected nonaggregate columns must appear in GROUP BY.

The analyzer also validates HAVING conditions and checks that set-operation inputs have matching column counts and compatible types.

**7. Preserve SQL projection and duplicate semantics**

Ordinary SELECT projections preserve duplicate rows at the logical-plan level.

SELECT DISTINCT introduces an explicit distinct operator when the query is not aggregating.

Grouping already produces one row per group, so the compiler avoids adding a redundant distinct operator above a grouped result.

This keeps duplicate elimination explicit rather than treating every projection as a set operation.

**8. Represent repeated aggregates only once**

The compiler identifies repeated aggregate expressions and registers each distinct aggregate once in the group_by operator.

For example, if the same COUNT expression appears more than once under different output aliases, the aggregate is computed once.

The projection preserves the requested output positions and aliases so multiple requested columns can refer to the same aggregate result.

**9. Preserve required operator ordering**

The compiler constructs logical plans from the SQL query clauses.

FROM establishes the input relation tree, followed by WHERE filtering, grouping, HAVING filtering, projection, duplicate elimination where required, sorting, and LIMIT.

A special case is required for ORDER BY on a column that is not selected.

Because the nonselected sort key would otherwise be unavailable after projection, the implementation places the sort below the projection when necessary.

ORDER BY on selected columns or output aliases can remain above the projection.

**10. Keep Module 3 independent of physical execution**

The SQL compiler produces logical operator dictionaries rather than choosing physical join algorithms or executing queries.

Physical optimization and operator selection are handled separately by Module 4 and the Module 2 execution engine.

This avoids mixing SQL language semantics with execution-cost decisions.

### Problems / AI Assistance

AI assistance was used during the broader project development and documentation process. The following issues are supported by the Module 3 implementation, regression tests, and recorded specification review.

**1. Clarifying the authoritative logical-plan schema**

The available Module 3 specification did not provide a separate logical-plan schema or sample catalog beyond the translation examples.

On November 5, the professor confirmed by email that the seven translation examples in Section 5 were the authoritative logical-plan JSON schema and that the existing Module 1 catalog should be reused.

I used this clarification to guide the compiler's output structure rather than introducing an independent catalog or incompatible logical-plan representation.

**2. Preserving duplicate semantics and aggregate aliases**

SQL projection semantics required particular care because ordinary SELECT does not automatically remove duplicate rows.

The implementation preserves bag semantics and inserts distinct only when required.

Another issue involved repeated aggregate expressions with different output aliases.

A simple mapping from aggregate expressions to output names cannot represent multiple requested output positions correctly.

I used positional projection metadata to preserve the requested aliases while computing each repeated aggregate only once.

Regression tests cover grouped DISTINCT, implicit aggregate grouping, and repeated aggregate aliases.

**3. Handling ORDER BY on a nonselected column**

The specification's logical-plan examples placed sorting above projection but did not define a representation for hidden sort keys.

This creates a plan-shape ambiguity for queries that sort by columns omitted from the SELECT list.

The implementation handles this by placing sorting before projection when the sort key would otherwise be unavailable.

It also rejects ORDER BY on a nonselected column in combination with DISTINCT when that ordering cannot be represented safely in the supported logical-plan format.

This remains a documented difference between the straightforward clause-to-operator translation and the special handling required for nonselected sort keys.

### Testing

I implemented six dedicated Module 3 test files:

- `tests/test_sql_tokenizer.py`
- `tests/test_sql_parser.py`
- `tests/test_sql_catalog.py`
- `tests/test_sql_semantic.py`
- `tests/test_sql_compiler.py`
- `tests/test_sql_cli.py`

The source contains 173 test functions across these files, including parametrized tests that may expand into additional pytest cases.

**Tokenizer tests** cover comments, string literals, escaped quotes, operators, multiple statements, source positions, and invalid input.

**Parser tests** cover supported SQL statements, nested queries, joins, Boolean precedence, grouping, aggregates, set operations, and malformed syntax.

**Catalog tests** verify schema retrieval, column order, declared types, case-sensitive names, unknown tables, and missing database files.

**Semantic tests** cover name resolution, ambiguity, type checking, grouping rules, aggregate validation, derived tables, and set-operation compatibility.

**Compiler tests** verify logical operator trees, projections, joins, grouping, aliases, sorting, LIMIT, DISTINCT, and set operations.

**CLI tests** cover parsing, AST display, semantic checking, JSON compilation, source files, error formatting, and unsupported statement types.

The dedicated Module 3 tests are also included in the complete repository regression suite.

### Command-Line Interface

The SQL front end provides three command-line operations.

**Parse:** Convert SQL text into an AST and optionally display the tree.

**Check:** Validate query names, types, grouping rules, and other supported semantic constraints against an existing database catalog.

**Compile:** Produce logical operator trees serialized as JSON.

The interface accepts SQL text directly or from a file.

Errors are reported using categories such as lexical, syntax, name, ambiguity, type, aggregate, and schema errors, with source locations where available.

### Results and Design Observations

The Module 3 implementation establishes a complete path from SQL source text to semantically validated logical operator trees.

The separation between parsing, semantic analysis, and compilation makes it possible to identify errors before generating an execution plan.

Reusing the Module 1 catalog avoids duplicating schema metadata and ensures that SQL name resolution uses the same table definitions as the storage engine.

The logical-plan compiler also provides the foundation for Module 4, which can apply logical rewrites, estimate costs, reorder supported joins, and lower eligible plans into physical execution operators.

The implementation deliberately supports a defined SQL subset rather than attempting unrestricted SQL compatibility.

In particular, CREATE TABLE and INSERT are recognized by the parser but are not compiled by the SELECT-oriented logical compiler.

The ORDER BY nonselected-column case remains a documented plan-format limitation.

Overall, Module 3 connects the storage engine's persistent schema information to a structured SQL query representation that later optimizer components can process.

## November 5–8, 2026 — Project 2, Module 4: Cost-Based Query Optimizer

### Goal

Implement a cost-based query optimizer that uses persistent database statistics to estimate query cardinalities, apply logical query rewrites, choose efficient join orders, and select physical execution algorithms.

The optimizer needed to integrate with the Module 1 storage engine, Module 2 execution operators, and Module 3 SQL logical plans while preserving query correctness.

### What I Did

I implemented the optimizer in `src/optimizer/`, including:

- Persistent table and column statistics collected through `ANALYZE`.
- Equi-depth histograms, distinct-value counts, minimum and maximum values, tuple counts, page counts, and average record widths.
- Equality, range, Boolean, and equijoin selectivity estimation.
- Recursive logical-plan cardinality and page-count estimation.
- Analytical page-I/O cost formulas for scans, external sorting, block nested-loop joins, hash joins, and sort-merge joins.
- Deterministic left-deep dynamic programming join ordering for two to six tables.
- Logical selection rewrites, including predicate splitting, pushdown, and supported cross-product-to-join conversions.
- Dependency-aware projection pushdown and redundant projection cleanup.
- Conservative SQL logical-plan integration.
- Cost-based physical plan lowering to the existing Module 2 execution operators.
- Deterministic fallback estimates when `ANALYZE` statistics are unavailable.

I also implemented experiments to compare baseline and optimized execution, measure cardinality estimation accuracy, isolate individual optimization passes, and investigate the effects of correlated predicates.

### Design Decisions

**1. Store statistics separately from the catalog**

I stored statistics in versioned JSON files under `optimizer_stats/` rather than changing the existing Module 1 catalog format.

This keeps statistics independent of catalog record-size restrictions and allows the optimizer to be added without modifying the original storage metadata design.

Statistics files are written using temporary files and atomic replacement to avoid leaving partially written results.

**2. Use equi-depth histograms and NDV-based estimates**

I used equi-depth histograms to improve selectivity estimation beyond fixed default values.

Equality predicates use histogram frequencies when possible and fall back to `1 / NDV`.

Numerical range predicates use interpolation, while unsupported or missing statistics use documented fallback selectivities.

I accepted the limitation that independent column histograms do not capture correlations between different attributes.

**3. Measure costs in estimated page I/O**

I chose page reads and writes as the optimizer's analytical cost unit instead of elapsed time.

This allows the optimizer to compare execution algorithms without depending on machine-specific timing measurements.

I kept analytical costs separate from actual buffer-manager counters because caching and operator implementation details can cause the two measurements to differ.

**4. Restrict join ordering to connected left-deep plans**

I implemented dynamic programming over connected table subsets, retaining one cheapest candidate per subset.

The search supports two to six tables and uses deterministic tie-breaking.

I restricted the search to left-deep plans rather than attempting to enumerate arbitrary bushy trees.

For intermediate joins, I also ensured that nested-loop costing does not assume an input reversal that would violate the required left-deep plan structure.

**5. Apply logical rewrites conservatively**

Selection predicates are pushed down only when their referenced columns can be resolved safely.

Projection pushdown preserves columns needed by selections, joins, sorting, and final output.

Unsupported or ambiguous transformations retain the original plan rather than risking incorrect query results.

**6. Separate logical optimization from physical lowering**

The logical optimization pipeline produces transformed logical plans.

Physical lowering separately chooses executable operators and validates whether the logical plan is supported by the Module 2 execution engine.

This separation makes the optimizer easier to test and allows unsupported physical plans to be rejected explicitly.

**7. Preserve deterministic behavior**

I used deterministic dataset generation, sorted DP inputs, stable tie-breaking, and repeatable experiment configurations.

This makes optimizer decisions and benchmark results reproducible.

### Problems / AI Assistance

AI assistance was used to review the optimizer architecture, develop implementation and regression tests, construct experiments, and interpret the resulting measurements.

I identified and corrected two significant issues during this process.

**1. Incorrect assumption that a cardinality error necessarily caused a worse physical plan**

During the initial cardinality evaluation, query Q20 showed a q-error of 3.333 for a filter involving the correlated columns `region` and `tier`.

The initial AI-assisted interpretation treated this estimation error as evidence that the optimizer had selected an inefficient physical join algorithm.

However, the observed cardinality error alone did not establish that the physical plan was different or that execution cost had increased.

I investigated this by searching approximately 8,000 configurations around the original workload. None demonstrated the required physical algorithm change for that specific case.

I then developed a broader analytical search, which identified 826 configurations where changing cardinality estimates could change the preferred algorithm.

Rather than presenting the analytical search as measured evidence, I constructed a separate deterministic correlated-column database and executed both the original and corrected plans.

The new experiment used 25,000 Customers rows and 6,000 Orders rows, with perfect correlation between `region` and `tier`.

The optimizer estimated 251 filtered Customers rows when the actual result contained 2,500 rows, giving a q-error of approximately 9.96.

At four buffer frames, the original estimate selected a nested-loop join, while the corrected estimate selected a hash join.

Both plans returned 600 rows, but the original plan recorded 159 buffer reads compared with 157 for the corrected plan.

This provided actual execution evidence of a cardinality-driven plan-selection difference.

I learned that an inaccurate estimate does not automatically imply an inefficient physical plan. A convincing optimizer failure case must demonstrate the causal relationship between the estimate, the selected plan, and measured execution behavior.

**2. Regression tests depended on an externally generated experiment database**

An initial version of the correlated-column regression tests expected the experiment database to have already been generated.

This made the tests dependent on local experiment files and could cause failures when running the test suite in a clean checkout.

I corrected the tests by introducing a module-scoped pytest fixture that creates a temporary database, generates the correlated tables, and collects the required statistics.

The tests now prepare their own input data and do not depend on a previously executed benchmark.

Seven dedicated correlation tests passed after this change.

I learned that regression tests should create or explicitly manage their dependencies rather than relying on artifacts left behind by manual experiments.

### Testing

I implemented and ran tests covering:

- Statistics validation, persistence, and loading.
- Histogram and selectivity estimation.
- Cardinality and page-count estimation.
- Physical cost formulas.
- Deterministic dynamic programming join ordering.
- SQL join-order integration.
- Logical selection and projection rewrites.
- Physical plan lowering and execution.
- Missing-statistics fallback behavior.
- Optimized versus baseline query-result equivalence.
- Correlated-column estimation and physical plan selection.

After completing the implementation and regression review, I ran:

```bash
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m pytest tests/ -q
```

Results:

```text
All checks passed!
213 files already formatted
1470 passed in 23.46s
```

All 1,470 tests passed, and both Ruff checks completed successfully.

### Experiments

I completed the following experiments.

**1. Baseline versus optimized execution**

I evaluated 20 queries on two deterministic datasets.

The 1× dataset contained 3,120 rows across four tables, while the 10× dataset contained 31,200 rows.

Aggregate physical buffer reads were unchanged between baseline and optimized execution:

- 1× dataset: 219 reads in both configurations.
- 10× dataset: 1,245 reads in both configurations.

This showed that logical optimization does not necessarily reduce physical reads when buffer caching and workload characteristics dominate the measured I/O.

**2. Optimizer ablation study**

I compared five configurations: fully optimized, no selection rewrites, no projection pushdown, no projection cleanup, and no join ordering.

All 200 configuration-query-scale evaluations completed successfully.

Projection pushdown had the largest measurable effect on operator-level reads.

On the 10× dataset, disabling projection pushdown increased operator reads from 2,063 to 2,784.

Disabling selection rewrites increased operator reads from 2,063 to 2,136.

Disabling projection cleanup or join ordering did not change aggregate reads in the tested workload.

**3. Cardinality estimation accuracy**

I evaluated cardinality estimates across 77 plan nodes for the 20-query workload at both dataset scales.

The median q-error was 1.000, and the worst q-error was 3.333.

The largest error occurred when filtering correlated columns, demonstrating the limitations of the independence assumption.

**4. Four-relation dynamic programming demonstration**

I generated a DP table using the stored statistics from the 1× benchmark database.

The four tables were Customers, Orders, Payments, and Shipments.

Using 32 buffer frames, the optimizer selected:

`Customers -> Orders -> Payments -> Shipments`

The selected plan had:

- 960 estimated output rows.
- 15 estimated output pages.
- An analytical I/O cost of 37.

The generated DP table demonstrated connected-subset enumeration, deterministic plan selection, and retention of intermediate estimates.

**5. Controlled correlated-column failure**

I generated a separate database with 25,000 correlated Customers rows and 6,000 Orders rows.

The filtered Customers cardinality was underestimated by approximately 9.96×.

At four buffer frames, correcting the estimate changed the selected algorithm from nested-loop join to hash join.

The corrected plan reduced measured buffer reads from 159 to 157, approximately 1.26%, while preserving the same 600 output rows.

At eight, sixteen, and thirty-two frames, both configurations selected nested-loop joins and recorded the same buffer-read count.

### Results and Design Observations

The experiments showed that projection pushdown provided the largest reduction in operator-level work, particularly at the larger dataset scale.

Selection rewrites also reduced operator reads, although the physical buffer-read totals remained unchanged.

The join-order optimizer successfully generated a deterministic four-relation left-deep plan, but the benchmark workload did not demonstrate a measurable aggregate I/O improvement from join reordering.

The correlated-column experiment demonstrated that independent single-column statistics can lead to substantial cardinality errors and, under suitable buffer constraints, a different physical join algorithm.

I also observed that the analytical cost model is an approximation. Actual execution behavior depends on caching, operator implementation, and available buffer frames.

The complete optimizer design is documented in `docs/DESIGN_M4.md`, and the experimental methodology and results are documented in `docs/REPORT_M4.md`.

### Next Steps

Perform a final consistency review of the Module 4 source code, tests, experiment artifacts, and documentation.

Verify the required submission files, rerun Ruff and pytest, and commit the completed Module 4 implementation only after the final review.