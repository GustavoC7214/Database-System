# Module 2 Design — Physical Query Execution Engine

## 1. Overview

Module 2 implements the physical execution engine for the relational database management system. Its purpose is to execute physical query plans over relations stored by Module 1, using a common iterator interface and a configurable shared page-buffer budget.

The execution engine supports sequential scans, filtering, projection, sorting, duplicate elimination, grouping and aggregation, three join algorithms, set operations, and limiting the number of output tuples.

The implementation uses page-based temporary files for operations that cannot process their inputs entirely as streams. This allows sorting, grouping, and joining relations larger than the configured buffer pool.

The design emphasizes:

- A consistent `open()`, `next()`, and `close()` operator lifecycle.
- A shared buffer pool with a configurable capacity of B frames.
- Disk-backed intermediate results for blocking operations.
- Correct handling of duplicate tuples and duplicate join keys.
- Deterministic cleanup of temporary files and buffer reservations.
- Execution statistics for analyzing algorithm behavior.
- Compatibility with physical plans expressed as JSON.

The implementation is written in Python and uses the storage infrastructure developed in Module 1.

## 2. Execution Architecture

### 2.1 Main components

The execution subsystem is located in `src/execution/`.

Its main components are:

| Component | Responsibility |
|---|---|
| `operator.py` | Common operator interface and execution counters |
| `page_manager.py` | Shared page-frame allocation, caching, pinning, and reservations |
| `physical_plan.py` | Construction of operator trees from physical-plan specifications |
| `plan_executor.py` | Execution of physical plans and collection of results and statistics |
| `cli.py` | Command-line execution and tracing |
| `seq_scan.py` | Sequential access to stored relations |
| `run_generation.py` | Creation of sorted temporary runs |
| `run_merge.py` | Multiway merging of sorted runs |
| `sort.py` | External merge-sort operator |
| `distinct.py`, `hash_distinct.py` | Sort-based and hash-based duplicate elimination |
| `group_by.py`, `hash_group_by.py` | Sort-based and hash-based aggregation |
| `nested_loop_join.py` | Block nested-loop equijoin |
| `sort_merge_join.py` | Sort-merge equijoin |
| `grace_hash_join.py` | Grace hash equijoin with overflow fallback |
| `union_all.py`, `union.py` | Bag union and distinct union |
| `set_operation.py`, `intersect.py`, `except_operator.py` | Disk-backed intersection and difference |
| `temp_page.py`, `temp_page_reader.py`, `temp_page_writer.py` | Temporary-page serialization and I/O |

### 2.2 Operator-tree execution

A physical plan is represented as a tree of operators. Each operator receives input from one or more child operators and produces output tuples for its parent.

For example:

```text
             Limit
               |
            Project
               |
             Sort
               |
             Filter
               |
            SeqScan
```

The `PhysicalPlanBuilder` recursively constructs the tree from a JSON plan specification.

The `PhysicalPlanExecutor` creates a shared page manager, builds the plan, opens the root operator, repeatedly requests tuples, and closes the root operator.

The execution sequence is conceptually:

```python
root.open()

try:
    while (row := root.next()) is not None:
        process(row)
finally:
    root.close()
```

In the current implementation, `PhysicalPlanExecutor` collects output tuples into a Python list before returning the execution result. The operator interfaces themselves are iterator-based, but the top-level result collection is not a streaming result sink.

This distinction matters for memory analysis: result collection may require memory proportional to the number of output tuples.

## 3. Iterator Model

### 3.1 Operator interface

All physical operators inherit from the common `Operator` base class.

The interface consists of:

- `open()`: Initialize execution state and prepare child operators or temporary storage.
- `next()`: Return the next output tuple, or `None` when exhausted.
- `close()`: Release open readers, temporary files, frame reservations, and child resources.
- `counters()`: Return execution statistics.

Each operator also exposes its output schema as a list of column-name and type pairs.

### 3.2 Streaming and blocking operators

Operators differ in how much input they must consume before producing results.

Streaming operators, such as `Filter`, `Project`, and `Limit`, can generally produce output incrementally.

Blocking operators, such as external `Sort`, may need to consume their complete input before producing the first output tuple.

The implementation handles blocking operations through temporary files rather than requiring the entire relation to remain in memory.

### 3.3 Lifecycle and cleanup

Operators are designed to release their resources through `close()`.

Cleanup is especially important for blocking operators because they may own:

- Temporary directories and files.
- Temporary-page readers and writers.
- Shared page-frame reservations.
- Python generators holding active readers.
- Child operators.

Where applicable, execution paths use `try`/`finally` or exception handling to ensure resources are released when an operation fails.

The executor also closes the root operator after execution, including when an exception occurs.

Integration tests cover normal completion, early termination, failed nested joins, and statistics after closure.

## 4. Shared Page Manager

### 4.1 Buffer-pool organization

`SharedPageManager` manages a fixed number of page frames shared by the execution engine.

The configured frame count is B, with a minimum supported value of four frames.

Each frame is a `bytearray` with the storage page size of 4096 bytes.

The manager maintains:

- A fixed array of page frames.
- A page table mapping stored pages to frames.
- Pin counts.
- Frame reservations for temporary operations.
- Cache-hit and page-I/O statistics.
- A replacement pointer.

All operators using the shared manager compete for the same page-frame capacity.

### 4.2 Pinning

A pinned frame cannot be selected for replacement while it is in use.

Sequential scans access stored pages through the page manager's pinning interface. Temporary algorithms reserve frames to use as input or output buffers.

A frame must be released or unpinned when the corresponding operation finishes.

### 4.3 Frame reservations

Temporary algorithms use `temporary_frames()` to reserve a specified number of shared frames.

The reservation mechanism prevents other operations from simultaneously claiming the same frames.

This provides an enforceable bound on the number of page frames allocated through the shared manager.

However, Python objects created outside these frames are not automatically charged against the frame budget.

### 4.4 Shared Page Cache Eviction

The execution engine uses a fixed number of 4096-byte page frames shared across all relations.

When the cache is full, an unpinned frame is selected using FIFO replacement.

Replacement pages are read directly into the selected frame to avoid allocating an additional page-sized temporary buffer.

If a replacement read fails, the victim's previous cache mapping is invalidated because its contents may have been partially overwritten.

The failed replacement is not inserted into the page table.

This prioritizes bounded page-buffer memory and cache correctness over preserving the previous cached page after an I/O failure.

### 4.5 Memory-accounting limitation

The shared page manager enforces the number of allocated page frames. This is not equivalent to an exact bound on the total Python heap used by an operator.

For example, the implementation also uses:

- Lists of decoded tuples.
- Dictionaries for hash tables and grouping states.
- Heap entries during multiway merging.
- Serialized tuple objects and sort keys.
- Operator metadata and temporary-file paths.

Some algorithms estimate the memory occupied by these structures using serialized tuple sizes and fixed overhead allowances.

These estimates are useful for deciding when to spill to disk, but they do not constitute exact measurements of Python object memory.

Therefore, the strongest directly demonstrated memory guarantee is the shared-frame allocation bound, not a strict bound on all process memory.

## 5. Sequential Scan

`SeqScan` provides sequential access to a stored relation.

During initialization, the operator obtains the relation's schema and storage information.

During execution, it reads relation pages through the shared page manager and produces tuples incrementally.

The scan uses qualified column names in its output schema so that columns from different relations can be distinguished in joins.

Its design avoids loading the complete relation into memory.

Sequential scanning also benefits from the shared cache when pages are already resident.

## 6. Filtering, Projection, and Limit

### 6.1 Filter

`Filter` evaluates a predicate against tuples supplied by its child operator.

Tuples satisfying the predicate are returned to the parent; other tuples are discarded.

The physical-plan builder supports predicates expressed through a condition string or explicit column, comparison, and value fields.

### 6.2 Project

`Project` selects the requested columns from each input tuple.

Projection is performed incrementally without requiring the entire input relation.

Column resolution uses the operator schema to identify the requested attributes.

### 6.3 Limit

`Limit` restricts the number of tuples returned to its parent.

Because it does not need to consume the entire child result, it can reduce work for streaming plans.

Early termination requires proper cleanup of any child operators that remain open.

## 7. External Merge Sort

### 7.1 Purpose

The `Sort` operator sorts input tuples by one or more specified columns, with ascending or descending direction.

It uses external merge sorting so that relations larger than the available page frames can be processed using temporary files.

The implementation consists of:

1. Initial run generation.
2. Intermediate multiway merging when necessary.
3. A final streamed merge or sequential read of the final run.

### 7.2 Initial run generation

`generate_sorted_runs()` consumes tuples from the child operator and stores serialized records in reserved page frames.

In the shared-frame implementation, the allocation is:

| Purpose | Frames |
|---|---:|
| Initial-run data | B − 2 |
| Temporary-run output | 1 |
| Available for child input | 1 |
| Total | B |

When the initial-run buffers are full, the records are decoded, sorted in Python, and written to a temporary run.

This means the effective initial-run storage allocation is B − 2 pages, not the B pages assumed by the simplest textbook external-sort model.

Additionally, decoded rows are temporarily held in a Python list during sorting. That list consumes memory outside the reserved page frames.

### 7.3 Intermediate merging

The implementation uses a merge fan-in of at most B − 1 runs.

For an intermediate merge, the allocation is:

| Purpose | Frames |
|---|---:|
| Input-run readers | Up to B − 1 |
| Output-run writer | 1 |
| Total | Up to B |

`merge_runs()` uses a heap containing the current tuple from each input run.

The heap selects the next tuple in sort order, after which the corresponding input reader advances.

Intermediate merge results are written to new temporary runs. Superseded input runs are deleted after successful merging.

### 7.4 Final output

When one run remains, `Sort` reads that run sequentially.

When multiple runs remain within the allowed fan-in, `Sort` merges them directly while returning tuples to its parent.

This avoids writing an additional complete temporary run solely for final output.

### 7.5 Theoretical cost model

For a textbook external merge sort with B pages available for initial runs, the initial number of runs is:

\[
R_0=\left\lceil\frac{N}{B}\right\rceil
\]

With merge fan-in B − 1, the number of merge passes is approximately:

\[
P_{\mathrm{merge}}=
\left\lceil\log_{B-1}(R_0)\right\rceil
\]

The total number of passes is:

\[
P_{\mathrm{total}}=1+P_{\mathrm{merge}}
\]

These formulas describe the conventional model.

The implementation's initial runs use B − 2 data frames, and its final output is streamed. Consequently, measured run counts, page reads, and page writes must be interpreted using the actual implementation rather than assuming an exact match with the simplified formula.

## 8. Duplicate Elimination

### 8.1 Sort-based distinct

The `Distinct` operator supports a sort-based mode.

It sorts tuples by all output columns, then compares each tuple with the previously emitted tuple.

Adjacent duplicates are suppressed.

Because equal tuples become adjacent after sorting, the operator does not need to retain a set containing every distinct tuple.

### 8.2 Hash-based distinct

`HashDistinct` partitions input tuples into B − 1 temporary files using a deterministic hash.

Each partition is processed independently.

The operator attempts to maintain a dictionary of previously seen tuples within an estimated memory allowance.

If a partition exceeds the allowance, it abandons the in-memory approach for that partition and uses external sorting to eliminate duplicates.

This fallback handles large or highly skewed partitions without allowing the dictionary to grow indefinitely according to the implementation's memory estimate.

## 9. Grouping and Aggregation

### 9.1 Supported aggregates

`GroupBy` supports:

- `COUNT`
- `SUM`
- `AVG`
- `MIN`
- `MAX`

Grouping keys and aggregate columns are resolved against the child schema.

The implementation validates supported aggregate functions and rejects unsupported argument combinations.

`SUM` and `AVG` require integer-typed input columns in the current implementation.

### 9.2 Sort-based grouping

For grouped aggregation, the operator sorts input tuples by their grouping keys.

It then processes consecutive tuples belonging to the same group, maintaining only the current group's aggregate state.

When the grouping key changes, the completed aggregate tuple is emitted.

For global aggregation without grouping keys, the operator can process the input directly.

### 9.3 Hash-based grouping

`HashGroupBy` partitions tuples by their grouping keys into B − 1 temporary files.

Each partition is processed using a dictionary mapping grouping keys to aggregate states.

The memory allowance is estimated from the grouping-key size and a fixed allowance for aggregate state.

If a partition exceeds that allowance, the implementation falls back to sort-based grouping.

### 9.4 Empty-input behavior

For grouped aggregation, an empty input produces no groups.

For global aggregation, `COUNT` over an empty input produces zero.

The current implementation raises an error for global empty-input aggregates other than `COUNT`, rather than returning SQL-style `NULL` values.

This is a deliberate behavior to describe accurately in the design and test documentation.

## 10. Block Nested-Loop Join

### 10.1 Algorithm

`NestedLoopJoin` implements an equality join using outer blocks and repeated inner scans.

Both child inputs are first materialized to temporary files.

During the join phase, the implementation loads an outer block, scans the inner temporary relation, and compares each inner tuple with the tuples in the current outer block.

Matching tuples are concatenated and returned.

### 10.2 Buffer allocation

The join phase reserves B − 1 frames:

| Purpose | Frames |
|---|---:|
| Outer-block allocation | B − 2 |
| Inner input | 1 |
| Remaining available frame | 1 |
| Total | B |

The current outer block is represented as a Python list of decoded tuples.

Its logical size is limited using serialized tuple-size estimates, but the Python list itself occupies additional heap memory.

### 10.3 Cost model

For outer relation M pages and inner relation N pages, the conventional block nested-loop join cost is:

\[
C_{\mathrm{BNLJ}}=
M+\left\lceil\frac{M}{B-2}\right\rceil N
\]

This describes the idealized join scan cost.

The implementation also writes both child inputs to temporary files before the join phase.

Therefore, measured operator I/O includes materialization overhead and may exceed the theoretical join-phase cost.

### 10.4 Join comparisons

For a complete equality join, the nested-loop algorithm conceptually compares every outer tuple against every inner tuple.

The expected number of tuple-key comparisons is:

\[
|R|\times|S|
\]

The actual counter is incremented during the join comparison loop.

## 11. Sort-Merge Join

### 11.1 Algorithm

`SortMergeJoin` sorts both input relations by their join keys and then merges them.

The implementation first materializes each sorted input into a temporary file.

It subsequently scans the two sorted relations, advancing the side with the smaller join key.

When the keys match, it produces joined tuples.

### 11.2 Duplicate-key handling

Duplicate join keys require special handling because every matching left tuple must be combined with every matching right tuple.

The implementation writes the matching right-side key group to a temporary file.

It then replays that group for each left tuple with the same key.

For example:

```text
Left keys:   1, 2, 2, 3
Right keys:  2, 2, 4

Matching key: 2
Output tuples: 2 × 2 = 4
```

This strategy supports duplicate groups larger than the available memory.

It also introduces additional temporary-file I/O, even for duplicate groups small enough to fit in memory.

### 11.3 Buffer allocation

The merge phase reserves three frames for:

- Left input.
- Right input.
- Duplicate-group storage or replay.

The minimum supported B value of four provides sufficient shared-frame capacity for this merge phase after the child sorting operations have completed.

### 11.4 Cost characteristics

The cost includes:

- Sorting the left relation.
- Sorting the right relation.
- Materializing both sorted relations.
- Scanning the sorted relations.
- Writing and replaying matching duplicate groups.

The duplicate-group I/O can become significant when many tuples share a join key.

## 12. Grace Hash Join

### 12.1 Algorithm

`GraceHashJoin` implements an equality join using hash partitioning.

The implementation:

1. Partitions the left relation into B − 1 temporary files.
2. Partitions the right relation using the same hash function.
3. Processes corresponding partition pairs.
4. Builds an in-memory hash table for the left partition when it fits the estimated memory allowance.
5. Probes the hash table with right-partition tuples.
6. Uses a disk-backed fallback when a left partition exceeds the allowance.

A deterministic BLAKE2b-based hash is used to assign join keys to partitions.

### 12.2 Partitioning memory

Partitioning reserves B − 1 output frames, leaving one frame available for child input.

The left and right partitioning phases are performed sequentially.

### 12.3 In-memory partition join

For each left partition, the implementation builds a dictionary mapping join keys to lists of matching left tuples.

The corresponding right partition is scanned, and each right tuple probes the dictionary.

All matching left tuples are combined with the right tuple.

This supports duplicate join keys.

### 12.4 Overflow handling

If the left partition exceeds its estimated memory allowance, the implementation switches to a disk-backed nested-loop fallback.

The fallback scans the left partition and repeatedly scans the corresponding right partition.

This avoids depending on successful recursive repartitioning when the input is heavily skewed.

However, it may perform many additional page reads.

### 12.5 Theoretical cost model

The idealized two-pass Grace hash join cost is:

\[
C_{\mathrm{GHJ}}=3(M+N)
\]

This consists of:

- Reading and partitioning both relations.
- Writing both sets of partitions.
- Reading the partitions again for the join.

The formula assumes that partitions can be processed without overflow.

The implementation's measured cost may differ because of temporary-file layout, page utilization, cache behavior, and overflow fallback.

The idealized formula is therefore a baseline, not a guaranteed measured cost.

## 13. Set Operations

### 13.1 UNION ALL

`UnionAll` concatenates two compatible input streams.

It preserves duplicate tuples.

Its output schema is based on the left input, and it validates matching column types.

### 13.2 UNION

`Union` is implemented as:

```text
       Distinct
          |
       UnionAll
       /      \
     Left     Right
```

The combined stream is passed through sort-based duplicate elimination.

This produces distinct union semantics.

### 13.3 INTERSECT

`Intersect` uses the shared `SortedSetOperation` implementation.

Both inputs are externally sorted and materialized.

A merge scan advances through the sorted inputs and emits tuples present in both relations.

Duplicate output tuples are suppressed.

### 13.4 EXCEPT

`Except` uses the same sorted-merge infrastructure.

It emits distinct left-side tuples that do not appear in the right input.

### 13.5 Schema compatibility

Set operations require compatible column counts and types.

The sorted set-operation implementation validates column counts and compares declared column types case-insensitively.

`UnionAll` compares the lists of declared column types directly.

### 13.6 Ordering consistency

`Sort` uses a dedicated sort-key transformation, whereas `SortedSetOperation` compares Python tuples directly during merging.

For the supported homogeneous value types, these approaches generally agree.

Nevertheless, the implementation does not use a single shared comparison function for all sorting and set-operation paths. Mixed-type or unexpected runtime values should therefore be considered a validation and testing concern.

## 14. Physical-Plan Construction

The `PhysicalPlanBuilder` converts JSON plan descriptions into executable operator trees.

Supported operator names include:

```text
SeqScan
Filter
Project
Limit
Sort
Distinct
GroupBy
NestedLoopJoin
SortMergeJoin
GraceHashJoin
UnionAll
Union
Intersect
Except
```

The builder also accepts lowercase aliases, including `hash_join` for `GraceHashJoin`.

It recursively constructs child operators, resolves relevant parameters, and passes the shared page manager to operators that require page buffers.

The builder supports loading plans from JSON objects and files.

Invalid operator names or invalid parameters produce errors rather than silently selecting an alternative algorithm.

## 15. Command-Line Interface

The execution engine exposes command-line commands for running and tracing physical plans.

The supported invocation pattern is:

```bash
python3 -m src.execution.cli run \
  --db DATABASE_DIRECTORY \
  --plan PLAN_FILE.json \
  --frames 32 \
  --json
```

Tracing is available through:

```bash
python3 -m src.execution.cli trace \
  --db DATABASE_DIRECTORY \
  --plan PLAN_FILE.json \
  --frames 32
```

The JSON execution result includes:

- `schema`
- `rows`
- `totals`

These provide the output schema, result tuples, and execution totals.

The frame count is configurable, allowing experiments to compare physical algorithms under different memory budgets.

## 16. Execution Statistics

### 16.1 Operator counters

The common operator counters include:

| Counter | Meaning |
|---|---|
| `tuples_out` | Number of tuples emitted |
| `comparisons` | Comparisons explicitly counted by the operator |
| `page_reads` | Page reads recorded by the operator |
| `page_writes` | Page writes recorded by the operator |

The meaning of `comparisons` depends on the algorithm.

For example, a nested-loop join counts tuple-key comparisons, while hash-based operations may count probes or processed entries.

These counters should not be interpreted as identical units of computational work across every operator.

### 16.2 Shared-buffer statistics

The page manager separately tracks physical page reads, writes, and cache hits.

These statistics describe page-manager activity and are distinct from operator-level temporary-file I/O counters.

### 16.3 Aggregated statistics

The executor collects statistics from the operator tree.

Operator-level totals and page-manager statistics should be reported separately to avoid implying that they measure exactly the same events.

The executor also records the root operator's output tuple count.

### 16.4 Statistics after close

Some operators preserve or transfer their child-algorithm counters when closing temporary sorting or hashing helpers.

This permits statistics to remain available after execution resources have been released.

Integration tests specifically cover join statistics after closure.

## 17. Experimental Evaluation

The Module 2 experiments are implemented under `experiments/m2/`.

They evaluate algorithm correctness, page-I/O behavior, execution time, buffer-size sensitivity, skew, and resource usage.

### 17.1 Join-cost experiment

`join_costs.py` compares:

- Block nested-loop join.
- Sort-merge join.
- Grace hash join.

The experiment uses three relation-size configurations and four frame budgets:

```text
B = 4, 16, 64, 256
```

The measured I/O is compared against the relevant textbook cost models.

Measured results include implementation-specific materialization, temporary-page activity, and overflow behavior.

### 17.2 External-sort experiment

`sort_passes.py` evaluates sorting under different combinations of input size and frame budget.

It includes inputs substantially larger than the buffer pool.

The theoretical pass count is calculated using the external merge-sort model.

The current experiment evidence should distinguish these calculated pass counts from directly instrumented pass counts.

### 17.3 Join crossover experiment

`join_crossover.py` studies changes in join performance when:

- The buffer budget varies while relation sizes remain fixed.
- Relation sizes vary while the buffer budget remains fixed.

The experiment records I/O and elapsed time.

Its purpose is to identify conditions under which one join algorithm becomes more attractive than another.

### 17.4 Hash-skew experiment

`hash_skew.py` compares uniformly distributed join keys against skewed inputs.

The skewed configuration concentrates approximately 40% of each input's tuples on a hot key.

This tests the impact of uneven partition sizes and expensive overflow handling.

Predicted partition overflow should be distinguished from directly observed overflow events unless those events are explicitly instrumented.

### 17.5 Memory-stress experiment

`memory_stress.py` sorts an input of approximately 20B pages with B = 4.

It records shared-frame observations during execution.

The experiment verifies that the observed reserved, cached, and pinned frame usage remains within the configured frame capacity.

It also checks that resources are released after execution.

The experiment does not measure all Python heap allocations and therefore does not independently prove a strict process-memory bound.

## 18. Testing and Validation

The execution engine is tested through unit and integration tests.

Coverage includes:

- Physical-plan construction.
- Sequential scans.
- Filtering and projection.
- Sorting.
- Sort-based and hash-based grouping.
- All three join algorithms.
- Qualified and reversed join conditions.
- Set operations.
- Duplicate elimination.
- Nested joins with B = 4.
- Larger nested joins with B = 4.
- Early termination through `Limit`.
- Cleanup after invalid nested plans.
- Operator statistics after closure.

The latest physical-plan integration test run completed successfully:

```text
35 passed in 0.28s
```

A previous full-suite run reported 733 passing tests, with Ruff and Pyright checks also passing. These are separate recorded validation runs rather than a claim that every check was rerun after the latest edits.

Passing tests provide evidence for the covered configurations. They do not establish correctness for every possible operator combination or input distribution.

## 19. Design Tradeoffs and Known Limitations

### 19.1 Materialization versus pipelining

Several join and set-operation implementations materialize their child results before processing them.

Advantages:

- Avoids keeping multiple complex child pipelines active during the join phase.
- Simplifies shared-frame coordination.
- Supports repeated scans.
- Makes temporary-file cleanup easier to manage.

Disadvantages:

- Adds page writes and reads.
- Increases temporary disk usage.
- Can delay the first output tuple.

### 19.2 Bounded frames versus Python heap usage

The page manager enforces a fixed shared-frame capacity.

However, decoded tuples, hash tables, grouping states, and final result lists occupy additional Python memory.

The implementation uses estimates and spill fallbacks to limit several intermediate structures, but it does not enforce an exact process-wide memory ceiling.

### 19.3 Hash overflow behavior

The Grace hash join uses a nested-loop fallback rather than recursive repartitioning.

This is straightforward and handles severe skew, but its I/O cost can be high.

Hash-based distinct and grouping use external-sort fallbacks for oversized partitions.

### 19.4 Sorting-pass model

The theoretical external-sort model assumes B-page initial runs.

The implementation reserves one frame for the child and one for output, leaving B − 2 frames for initial-run data.

As a result, theoretical and actual run counts should not be presented as identical without measurement.

### 19.5 Comparison semantics

The execution engine primarily supports integer, real, and string tuple values.

Different algorithms implement comparisons through sorting keys, Python tuple comparisons, equality checks, or hash lookups.

A centralized typed comparison abstraction would improve consistency and simplify edge-case validation.

### 19.6 Result materialization

Although the operator tree follows an iterator interface, the executor currently accumulates final output rows in a Python list.

This makes the API convenient for tests and JSON output but means total result memory grows with output size.

A streaming result sink would reduce that limitation.

## 20. Future Improvements

Potential improvements include:

1. Instrumenting actual sort-run counts and merge passes.
2. Recording actual hash partition sizes and overflow events.
3. Unifying typed comparison semantics across operators.
4. Reducing extra materialization in joins and set operations.
5. Replacing Python tuple lists in initial-run generation with a more tightly accounted in-frame sorting representation.
6. Improving Python heap-memory accounting for hash tables and grouping states.
7. Supporting streaming final-result output.
8. Adding additional nested-plan stress tests for combinations of blocking operators.

These are improvement opportunities and should not be described as completed features.

## 21. Conclusion

Module 2 provides a functioning physical query execution engine built around the iterator model and a shared page manager.

The engine implements the required families of relational operators, uses page-based temporary files for blocking operations, and supports multiple algorithms for sorting, duplicate elimination, grouping, and joining.

Its design makes algorithmic tradeoffs observable through execution statistics and experiments.

The shared page manager enforces a fixed page-frame capacity, while temporary-file strategies allow relations larger than the buffer pool to be processed.

The main qualifications are that Python-level memory is not accounted for exactly, several operators incur additional materialization I/O, and some experimental metrics remain theoretical rather than directly instrumented.

These distinctions are important for an accurate evaluation of the implementation and its relationship to textbook external-memory algorithms.
