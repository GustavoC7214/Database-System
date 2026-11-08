# Module 4 — Cost-Based Query Optimizer Design

## 1. Overview

Module 4 extends the database system developed in Modules 1–3 with statistics collection, cardinality estimation, logical query optimization, join-order optimization, and cost-based physical plan selection.

The optimizer operates on the logical JSON query plans produced by the Module 3 SQL compiler. It uses statistics collected from the Module 1 storage engine to estimate query cardinalities and page-I/O costs, then applies supported transformations and selects physical operators implemented in Module 2.

The primary objectives are to:

- Collect and persist table and column statistics.
- Estimate predicate selectivity, intermediate cardinalities, and page counts.
- Compare physical execution algorithms using analytical I/O costs.
- Optimize connected equijoin orders using dynamic programming.
- Apply semantics-preserving selection and projection rewrites.
- Produce executable physical plans for supported SQL queries.
- Preserve query correctness and deterministic optimizer behavior.

The implementation prioritizes conservative transformations, reproducibility, and compatibility with the existing database architecture.

## 2. Architecture

The optimizer is implemented in `src/optimizer/` and is organized into the following components.

| Component | Main implementation |
|---|---|
| Statistics representation and persistence | `statistics.py` |
| Statistics collection | `analyze.py`, `histogram.py` |
| Selectivity estimation | `selectivity.py` |
| Cardinality and page estimation | `cardinality.py`, `estimator.py` |
| Physical I/O cost formulas | `cost.py`, `plan_cost.py` |
| Dynamic programming join ordering | `join_order.py` |
| SQL join-order integration | `sql_join_order.py` |
| Selection rewrites | `rewrites.py` |
| Projection pushdown | `projection_pushdown.py` |
| Logical optimization pipeline | `pipeline.py` |
| SQL compilation integration | `sql_pipeline.py` |
| Physical plan generation | `physical_lowering.py` |
| Missing-statistics fallback | `statistics_fallback.py` |

The main processing flow is:

```text
SQL query
    |
    v
Module 3 SQL compiler
    |
    v
Logical JSON plan
    |
    v
Logical rewrite pipeline (optional)
    |
    v
Eligible join-order optimization
    |
    v
Optimized logical plan
    |
    v
Cardinality estimation + physical cost comparison
    |
    v
Physical plan lowering
    |
    v
Module 2 execution operators
    |
    v
Query results and execution statistics
```

Statistics collection is performed separately using `ANALYZE`. Its results are consumed by the planning stages.

The SQL optimization pipeline returns logical plans; physical lowering is a separate operation.

## 3. Statistics Collection

### 3.1 ANALYZE

`analyze_table()` in `src/optimizer/analyze.py` collects statistics for a specified table.

The base table is scanned once using the existing `SeqScan` execution operator. Column values are written to temporary streams and sorted using the Module 2 external sorting operator.

The resulting statistics include:

- Number of tuples.
- Number of data pages.
- Average encoded record width.
- Number of distinct values (NDV) for each column.
- Minimum and maximum column values.
- Equi-depth column histograms.

Data-page counts exclude directory pages. Average width is calculated using the encoded record representation.

The implementation requires at least four buffer frames for `ANALYZE`.

### 3.2 Histogram representation

Each histogram bucket contains:

- `lower`: minimum bucket value.
- `upper`: maximum bucket value.
- `count`: number of values represented.
- `ndv`: number of distinct values in the bucket.

Histograms support more informed selectivity estimates than a single table-wide default.

The implementation uses individual column histograms. It does not currently maintain joint distributions or multicolumn correlation statistics.

### 3.3 Persistent statistics

`StatisticsStore` saves statistics as versioned JSON files:

`<database_directory>/optimizer_stats/<table>.json`

Statistics are stored independently of the Module 1 catalog, avoiding changes to the existing catalog record format.

Writes use a temporary file followed by an atomic replacement. The serialized representation uses deterministic JSON formatting.

The store validates statistics when constructing the associated data objects and rejects unsupported statistics versions during loading.

If a table has not been analyzed, `StatisticsStore.load()` returns `None`.

## 4. Selectivity and Cardinality Estimation

### 4.1 Equality predicates

Equality selectivity is estimated using matching histogram buckets when available.

For a value contained in a bucket, the estimated frequency is based on the bucket's tuple count divided by its NDV. Contributions from matching buckets are combined.

If a histogram-based estimate is unavailable, the estimator uses:

`Selectivity(A = v) = 1 / NDV(A)`

When column statistics are entirely unavailable, the default equality selectivity is 0.1.

Values outside known minimum and maximum boundaries have zero estimated selectivity.

### 4.2 Range predicates

For numerical columns, range selectivity uses histogram bucket boundaries and interpolation.

When no histogram is available, numerical ranges are estimated using the column minimum and maximum.

String ranges use a conservative fallback because lexicographic distances cannot be interpreted as numerical distances.

The default range selectivity without column statistics is one-third.

### 4.3 Boolean predicates

For conjunctive predicates, the estimator assumes independence:

`P(A AND B) = P(A) × P(B)`

For disjunctive predicates:

`P(A OR B) = P(A) + P(B) − P(A) × P(B)`

Negation is estimated as:

`P(NOT A) = 1 − P(A)`

All selectivities are clamped to the interval [0, 1].

The independence assumption is an important limitation when columns are strongly correlated.

### 4.4 Cardinality estimation

The estimated number of output rows is calculated as:

`Estimated rows = ceil(Input rows × Selectivity)`

A nonzero estimate produces at least one row. Zero selectivity or an empty input produces zero rows.

Intermediate page counts are estimated using:

`Estimated pages = ceil(Estimated rows × Average row width / Page size)`

Nonempty relations are assigned at least one estimated page.

The implementation uses the storage engine's configured page size.

### 4.5 Equality join cardinality

For an equality join, selectivity is estimated using:

`1 / max(NDV(left key), NDV(right key))`

When the known value ranges do not overlap, join selectivity is zero.

The resulting join cardinality is estimated by multiplying the left and right input cardinalities by the estimated join selectivity.

Missing column statistics use a default join selectivity of 0.1.

### 4.6 Logical plan estimation

`LogicalPlanEstimator` recursively estimates properties of logical plan nodes.

Each `NodeEstimate` contains:

- The annotated logical plan.
- Estimated rows.
- Estimated pages.
- Estimated row width.
- Available column estimates.

The estimator preserves source-table cardinalities alongside column statistics so that predicate frequencies can be normalized against their original source relation.

The estimator does not mutate the input logical plan.

## 5. Physical I/O Cost Model

The cost model is implemented in `src/optimizer/cost.py`.

Costs represent estimated page reads and writes, not elapsed execution time.

Let:

- `M` be the number of pages in the left or outer input.
- `N` be the number of pages in the right or inner input.
- `B` be the number of available buffer frames.

### 5.1 Sequential scan

`Cost(scan) = M`

A sequential scan reads each input page once.

### 5.2 Streaming selection and projection

Selections and projections have zero additional modeled page I/O beyond their child operators.

These operators process tuples without requiring separate materialization in the analytical model.

### 5.3 Block nested-loop join

`Cost(BNLJ) = M + ceil(M / (B − 2)) × N`

The model allocates `B − 2` buffer pages to the outer relation.

For a join between two base-table scans, the optimizer may compare both outer/inner orientations and select the cheaper one.

For an intermediate left-deep join, the accumulated intermediate relation remains the left input. The cost model does not assume an orientation that would violate the required plan shape.

### 5.4 Hash join

`Cost(Hash Join) = 3 × (M + N)`

This represents a one-level Grace hash join.

The analytical model assumes that partitions fit during the build/probe phase. Recursive repartitioning is not included in this formula.

### 5.5 External merge sort

The initial sort pass creates runs of up to `B` pages. Subsequent merge passes combine up to `B − 1` runs.

The sort model counts reads and writes for nonfinal passes and assumes the final output is pipelined.

If `p` is the total number of sort passes:

`Cost(Sort) = 2M(p − 1) + M`

### 5.6 Sort-merge join

`Cost(SMJ) = Cost(Sort(M)) + Cost(Sort(N)) + M + N`

The model assumes matching-key groups can be processed without additional spill I/O during the merge phase.

### 5.7 Algorithm selection

The optimizer evaluates supported join algorithms and chooses the minimum estimated I/O cost.

Ties are resolved deterministically in the following order:

1. Nested-loop join.
2. Hash join.
3. Sort-merge join.

`PhysicalCostEstimator` recursively reports local and total analytical costs through `CostedPlan` objects.

These estimates should not be interpreted as exact predictions of measured buffer traffic. Actual execution depends on operator implementation, caching, pipelining, and intermediate materialization.

## 6. Dynamic Programming Join Ordering

### 6.1 Supported search space

`optimize_join_order()` implements deterministic left-deep dynamic programming for connected equijoin graphs containing between two and six tables.

A left-deep plan adds one base relation at a time to an existing intermediate result.

The implementation retains one cheapest known plan for each table subset.

### 6.2 DP state

Each `DPEntry` stores:

- The subset of included tables.
- The selected join order.
- The logical plan.
- Estimated output rows.
- Estimated output pages.
- Estimated row width.
- Cumulative analytical I/O cost.

Singleton states are initialized using base-table scans and their stored page counts.

### 6.3 DP recurrence

For each subset containing at least two tables, the optimizer considers removing each possible rightmost base table.

The remaining subset must already have a valid retained plan, and the added table must be connected to that subset by at least one equality predicate.

For each valid expansion, the optimizer:

1. Retrieves the best retained plan for the smaller subset.
2. Identifies connecting join predicates.
3. Estimates the join algorithm cost.
4. Estimates output cardinality and width.
5. Constructs the candidate left-deep plan.
6. Compares the candidate with other plans for the same subset.

For larger intermediate joins, the candidate score adds the retained left-subplan cost to the new join cost. The two-relation case uses its selected join cost as implemented.

The cheapest candidate is retained using estimated cost followed by join order as a deterministic tie-breaker.

### 6.4 Join graph restrictions

Disconnected join graphs are rejected by the standalone DP optimizer.

Duplicate join predicates and invalid table references are validated.

The optimizer can preserve multiple connecting equality predicates in the generated logical join condition, although downstream physical lowering currently supports only a single equality predicate per physical join node.

### 6.5 SQL integration

`optimize_sql_join_order()` applies DP optimization only to eligible SQL logical subtrees.

The extraction rules require:

- Unaliased base-table scans.
- Inner equality joins.
- Qualified column references.
- Join predicates connecting opposite inputs.
- No repeated table references within the candidate tree.
- Available table statistics and schema information.
- Two to six distinct tables.

Unsupported subtrees retain their original structure.

This is deliberately conservative: the optimizer does not reorder arbitrary joins across selection, projection, aggregation, or alias boundaries.

### 6.6 Determinism

Table names and join edges are sorted, and candidate comparisons use stable tie-breaking rules.

`format_dp_table()` provides a deterministic representation of retained DP states for debugging and reporting.

## 7. Logical Query Rewrites

### 7.1 Selection rewrites

`src/optimizer/rewrites.py` performs semantics-preserving transformations on logical JSON plans.

Supported transformations include:

- Splitting conjunctions into individual predicates.
- Merging adjacent selections.
- Pushing predicates into the appropriate side of joins and cross products.
- Converting supported cross products with equality predicates into joins.
- Translating predicates through supported rename operations.
- Pushing grouping-key predicates below grouping operations.
- Distributing safe selections across `UNION` and `UNION ALL`.

Predicates are moved only when their column references can be resolved safely.

Predicates referencing both sides of a join are not incorrectly pushed into a single input.

Unknown or ambiguous column references prevent unsafe transformations.

### 7.2 Projection pushdown

`src/optimizer/projection_pushdown.py` tracks columns required by the final projection and intermediate operators.

It preserves columns needed for:

- Selection predicates.
- Join conditions.
- Sort keys.
- Final query output.

For joins, required columns are divided between the left and right inputs.

An explicit root projection is required. Plans without one remain unchanged because their complete output schema may be observable.

Aliased or computed projection expressions are not pushed down without a safe expression-to-source mapping.

### 7.3 Projection cleanup

`cleanup_projections()` removes safe redundant adjacent projections when both use the same ordered column list and neither performs output renaming.

It does not arbitrarily reorder output columns or remove projections whose semantics may differ.

### 7.4 Rewrite pipeline

`optimize_logical_plan()` applies the enabled passes in this order:

1. Selection rewrites.
2. Projection pushdown.
3. Projection cleanup.

Each pass can be independently enabled or disabled.

The original input plan is not mutated.

This configurability supports ablation experiments that isolate the effects of individual optimization stages.

## 8. Physical Plan Lowering

`lower_physical_plan()` translates supported logical JSON plans into the physical plan format consumed by the Module 2 executor.

Supported transformations include:

| Logical operation | Physical operation |
|---|---|
| `scan` | `seqscan` |
| `select` | `filter` |
| `project` | `project` |
| `limit` | `limit` |
| `join` | Selected physical join algorithm |

Supported selection conditions include conjunctions of column-to-literal comparisons.

Physical joins require a single column-to-column equality predicate.

The lowerer validates column ownership, table schemas, join keys, projection names, and operator compatibility.

For base-table scans, it uses actual page counts from stored statistics. For intermediate relations, it uses the logical cardinality estimator.

The `join_algorithm` parameter can force a supported join algorithm for controlled experiments.

The `preserve_join_order` parameter prevents applicable join-input reorientation.

Unsupported logical structures raise `UnsupportedPhysicalPlan` instead of silently producing potentially incorrect execution plans.

Physical lowering does not currently support every logical operator handled by the broader estimation and rewrite layers.

## 9. Missing Statistics

`statistics_fallback.py` supplies deterministic planning estimates for tables that have not been analyzed.

The fallback values are:

| Statistic | Value |
|---|---:|
| Rows | 1,000 |
| Pages | 20 |
| Average row width | 32 bytes |

Fallback statistics are used for planning only.

They are not persisted and do not overwrite genuine `ANALYZE` results.

The optimizer can therefore construct supported physical plans even when some table statistics are unavailable, although the resulting cost estimates may be less accurate.

## 10. Correctness and Safety

The optimizer uses several conservative design rules.

**Nonmutation:** Logical rewrites and join-order integration return transformed copies rather than modifying caller-owned plans.

**Schema awareness:** Predicates and projections are moved only when required columns can be resolved.

**Restricted join reordering:** Only supported equijoin trees are reordered.

**Stable selection:** Deterministic sorting and tie-breaking make optimization reproducible.

**Explicit unsupported cases:** Physical lowering rejects unsupported operations rather than inventing execution behavior.

**Execution validation:** Optimized and baseline plans are compared using query-result equivalence tests.

**Independent measurements:** Analytical cost estimates are distinguished from measured execution counters and buffer-manager statistics.

These choices prioritize correctness over aggressive optimization.

## 11. Known Limitations

### 11.1 Correlated predicates

Column statistics are maintained independently.

For correlated columns, multiplying individual selectivities can substantially underestimate or overestimate the number of matching rows.

The experimental report documents a case where this error changes physical join selection and increases measured buffer reads.

### 11.2 Restricted join-order search

The DP optimizer searches connected left-deep plans, not arbitrary bushy join trees.

It retains one best candidate per subset and does not maintain multiple interesting physical properties, such as alternative output sort orders.

### 11.3 Limited SQL lowering

Physical lowering supports a restricted subset of logical operators and predicates.

Aliases, cross joins, grouping, and more complex physical join conditions are outside its supported lowering scope.

### 11.4 Analytical cost approximations

The I/O formulas simplify execution behavior.

They do not fully model buffer-cache effects, repeated access patterns, recursive hash partitioning, or every intermediate-materialization cost.

Consequently, an analytically cheaper plan may not always minimize measured buffer traffic.

### 11.5 Buffer-frame constraints

The analytical cost functions permit some calculations with three frames.

The shared page manager used for actual physical execution requires at least four frames.

Executable experiments therefore use four or more frames.

## 12. Testing and Evaluation

Module 4 is evaluated using:

- Unit tests for statistics, selectivity, cardinality, and cost formulas.
- Tests for deterministic DP join ordering.
- Logical rewrite equivalence and safety tests.
- Physical plan execution tests.
- Missing-statistics fallback tests.
- A deterministic 20-query benchmark workload.
- Experiments at 1× and 10× dataset scales.
- Optimizer ablation experiments.
- Cardinality estimation error measurements.
- A correlated-column failure experiment.

The correlated-column integration tests generate their own temporary database, run `ANALYZE`, compare original and corrected plan selection, and verify equivalent query results.

At the latest full validation, the repository passed **1,470 pytest tests**, with clean Ruff lint and formatting checks.

Detailed benchmark methodology, measurements, cardinality q-errors, and experimental interpretation are recorded separately in `docs/REPORT_M4.md`.

## 13. Conclusion

Module 4 adds a functioning cost-based optimization layer to the existing database system.

The implementation combines persistent statistics, histogram-based selectivity estimates, recursive cardinality estimation, analytical I/O costing, deterministic left-deep join ordering, conservative logical rewrites, and physical plan selection.

The optimizer integrates with the earlier storage, SQL compilation, and execution modules without requiring a redesign of those components.

Its principal tradeoff is a deliberately restricted optimization search space in exchange for deterministic behavior, implementation simplicity, and preservation of query correctness.

The accompanying experiments evaluate both the benefits and limitations of these decisions.