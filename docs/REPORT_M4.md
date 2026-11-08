# Module 4 — Query Optimizer Experimental Report

## 1. Introduction

This report evaluates the correctness, performance, and limitations of the cost-based query optimizer implemented in Module 4.

The evaluation examines whether logical rewrites, join-order optimization, and physical algorithm selection improve execution efficiency while preserving query results.

The experiments measure both analytical cost estimates and actual execution statistics. Particular attention is given to cardinality estimation accuracy and the effects of correlated predicates on physical plan selection.

## 2. Experimental Setup

### 2.1 Database workloads

A deterministic dataset generator was used to construct two benchmark databases.

| Property | 1× dataset | 10× dataset |
|---|---:|---:|
| Customers | 240 | 2,400 |
| Orders | 960 | 9,600 |
| Payments | 960 | 9,600 |
| Shipments | 960 | 9,600 |
| Total rows | 3,120 | 31,200 |

The benchmark tables use integer-valued attributes and deterministic relationships.

The 10× database provides a larger workload for observing the effects of relation size on query execution.

### 2.2 Query workload

The evaluation uses 20 queries designed to exercise supported combinations of:

- Table scans.
- Equality and range selections.
- Multiple conjunctive predicates.
- Projections.
- Equijoins.
- Multi-relation query plans.

Queries were evaluated with baseline and optimized execution configurations.

### 2.3 Measurements

The experiments distinguish:

**Buffer I/O:** Physical page reads and writes recorded by the shared buffer manager.

**Operator reads:** Logical read activity recorded by execution operators.

**Cardinality estimation error:** The difference between estimated and actual intermediate result sizes.

**Result correctness:** Equivalence of baseline and optimized query results.

Analytical optimizer costs are not treated as direct measurements of physical disk traffic.

## 3. Baseline Versus Optimized Execution

### 3.1 Physical buffer reads

The recorded aggregate physical buffer reads were:

| Dataset | Baseline reads | Optimized reads | Baseline / optimized |
|---|---:|---:|---:|
| 1× | 219 | 219 | 1.00× |
| 10× | 1,245 | 1,245 | 1.00× |

The optimized configurations did not reduce aggregate physical buffer reads in this comparison.

This does not imply that the optimizer performed no useful transformations. The benchmark uses a relatively small collection of tables and a shared buffer manager, so some logical reductions in operator work do not translate into fewer physical reads.

### 3.2 Interpretation

The principal finding is that optimizer effectiveness depends on the metric being measured.

An optimization may reduce intermediate tuple processing or repeated operator-level accesses without reducing physical I/O when pages are already resident in the buffer pool.

Consequently, the report evaluates physical I/O and operator-level work separately.

## 4. Optimizer Ablation Study

### 4.1 Methodology

Five optimizer configurations were compared:

1. Fully optimized.
2. Selection rewrites disabled.
3. Projection pushdown disabled.
4. Projection cleanup disabled.
5. Join ordering disabled.

Each configuration was evaluated across the 20-query workload at both dataset scales, producing 200 configuration-query-scale evaluations.

### 4.2 Results

| Configuration | 1× buffer reads | 1× operator reads | 10× buffer reads | 10× operator reads |
|---|---:|---:|---:|---:|
| Fully optimized | 219 | 291 | 1,245 | 2,063 |
| No selection rewrites | 219 | 294 | 1,245 | 2,136 |
| No projection pushdown | 219 | 330 | 1,248 | 2,784 |
| No projection cleanup | 219 | 291 | 1,245 | 2,063 |
| No join ordering | 219 | 291 | 1,245 | 2,063 |

All 200 ablation evaluations completed successfully.

### 4.3 Selection rewrites

Disabling selection rewrites increased operator reads:

- From 291 to 294 on the 1× dataset.
- From 2,063 to 2,136 on the 10× dataset.

The larger dataset showed a reduction of approximately 3.4% in operator reads when selection rewrites were enabled, relative to the configuration without them.

This is consistent with pushing eligible filters closer to their input relations and reducing unnecessary downstream processing.

### 4.4 Projection pushdown

Projection pushdown produced the largest measurable improvement in the ablation study.

On the 1× dataset, operator reads decreased from 330 to 291, approximately 11.8%.

On the 10× dataset, operator reads decreased from 2,784 to 2,063, approximately 25.9%.

Physical buffer reads on the 10× dataset also decreased slightly, from 1,248 to 1,245.

These results indicate that reducing the width of intermediate tuples becomes more beneficial as the workload grows.

### 4.5 Projection cleanup

Disabling projection cleanup did not change the aggregate read measurements in this workload.

This does not establish that the pass is unnecessary. Its role is to remove redundant projections safely, and its measurable benefit depends on whether such projections appear in the workload.

### 4.6 Join ordering

Disabling join ordering produced the same aggregate measurements as the fully optimized configuration.

The tested join structures therefore did not demonstrate a measurable aggregate I/O benefit from reordering.

The dynamic programming implementation remains useful for supported connected equijoin graphs, but the benchmark does not justify claiming a measured join-order speedup.

## 5. Cardinality Estimation Accuracy

### 5.1 Q-error metric

Cardinality accuracy was evaluated using q-error:

`Q-error = max(Estimated / Actual, Actual / Estimated)`

For nonzero estimated and actual cardinalities, a q-error of 1 indicates an exact estimate.

Larger values indicate less accurate estimates.

### 5.2 Results

The cardinality evaluation covered 77 plan nodes across the 20-query workload at both dataset scales.

| Metric | Result |
|---|---:|
| Median q-error | 1.000 |
| Worst q-error | 3.333 |
| Worst-performing query | Q20 |

The median indicates that at least half of the evaluated estimates were exact.

The largest error occurred for:

```sql
SELECT *
FROM Customers
WHERE region = 1 AND tier = 1;
```

The `region` and `tier` columns are strongly correlated in the generated dataset.

### 5.3 Correlation limitation

The estimator calculates conjunctive selectivity by multiplying the individual predicate selectivities.

For correlated columns, this independence assumption can substantially underestimate the actual number of matching rows.

On the 10× dataset, the filtered Customers cardinality was estimated as 180 rows, compared with 600 actual rows.

This corresponds to:

`Q-error = 600 / 180 = 3.333`

The error also propagates to dependent join estimates.

This experiment identifies a limitation of independent single-column statistics, but by itself does not demonstrate that the error changes the selected physical plan.

## 6. Correlated-Column Physical Plan Failure

### 6.1 Objective

A separate experiment was designed to determine whether cardinality estimation error could change physical join algorithm selection and increase actual buffer reads.

Unlike the standard Q20 workload, this experiment uses a larger filtered relation and an independently generated Orders table.

### 6.2 Dataset

| Table | Rows | Pages |
|---|---:|---:|
| CorrelatedCustomers | 25,000 | 123 |
| CorrelatedOrders | 6,000 | 30 |
| Total | 31,000 | 153 |

In `CorrelatedCustomers`, the `region` and `tier` columns are perfectly correlated.

The experiment filters for both columns having the value 1, then joins the filtered Customers relation to Orders using customer identifiers.

### 6.3 Cardinality error

| Measurement | Value |
|---|---:|
| Estimated filtered rows | 251 |
| Actual filtered rows | 2,500 |
| Estimated filtered pages | 1 |
| Actual filtered pages | 10 |
| Cardinality q-error | 9.9602 |

The optimizer significantly underestimates the filtered relation because it assumes that the two predicates are independent.

### 6.4 Counterfactual plan comparison

The experiment compares the original estimated cardinality with a corrected estimate.

The correction is applied during planning, without changing the underlying query data or result semantics.

| Buffer frames | Original algorithm | Corrected algorithm |
|---|---|---|
| 4 | Nested-loop join | Hash join |
| 8 | Nested-loop join | Nested-loop join |
| 16 | Nested-loop join | Nested-loop join |
| 32 | Nested-loop join | Nested-loop join |

At four buffer frames, correcting the cardinality estimate changes the chosen physical algorithm.

At larger buffer sizes, the selected algorithm remains unchanged.

### 6.5 Actual execution measurements

| Frames | Plan | Output rows | Buffer reads | Buffer writes |
|---|---|---:|---:|---:|
| 4 | Original nested-loop | 600 | 159 | 0 |
| 4 | Corrected hash join | 600 | 157 | 0 |
| 8 | Original nested-loop | 600 | 159 | 0 |
| 8 | Corrected nested-loop | 600 | 159 | 0 |
| 16 | Original nested-loop | 600 | 159 | 0 |
| 16 | Corrected nested-loop | 600 | 159 | 0 |
| 32 | Original nested-loop | 600 | 159 | 0 |
| 32 | Corrected nested-loop | 600 | 159 | 0 |

All original and corrected plans returned equivalent results.

At four frames, correcting the estimate reduced measured buffer reads from 159 to 157.

The relative reduction was approximately 1.26%.

### 6.6 Interpretation

This experiment establishes a causal connection between cardinality estimation error and physical plan selection in the tested configuration.

The incorrect estimate favors a nested-loop join. Correcting the estimate causes the optimizer to select a hash join, which requires two fewer measured buffer reads.

The improvement is small in absolute terms, and the plan difference disappears at larger buffer capacities.

The result demonstrates that cardinality estimation quality can influence plan selection without implying that every estimation error necessarily produces a worse plan.

## 7. Dynamic Programming Join-Order Demonstration

### 7.1 Objective

This experiment demonstrates the deterministic left-deep dynamic programming join-order optimizer using four relations from the 1× benchmark database.

The optimizer evaluates connected join orders using statistics collected by `ANALYZE` and retains the cheapest candidate for each table subset.

### 7.2 Input Relations

The experiment uses the following base-table statistics:

| Table | Rows | Pages |
|---|---:|---:|
| Customers | 240 | 2 |
| Orders | 960 | 5 |
| Payments | 960 | 5 |
| Shipments | 960 | 5 |

The join predicates are:

```sql
Customers.cid = Orders.cid
Orders.oid = Payments.oid
Orders.oid = Shipments.oid
```

The experiment uses 32 buffer frames.

### 7.3 Dynamic Programming Table

The following table was generated directly using `format_dp_table()` and `optimize_join_order()`.

| Table subset | Selected join order | Est. rows | Est. pages | Est. I/O |
|---|---|---:|---:|---:|
| {Customers} | Customers | 240 | 2 | 2 |
| {Orders} | Orders | 960 | 5 | 5 |
| {Payments} | Payments | 960 | 5 | 5 |
| {Shipments} | Shipments | 960 | 5 | 5 |
| {Customers, Orders} | Customers → Orders | 960 | 8 | 7 |
| {Orders, Payments} | Orders → Payments | 960 | 8 | 10 |
| {Orders, Shipments} | Orders → Shipments | 960 | 8 | 10 |
| {Customers, Orders, Payments} | Customers → Orders → Payments | 960 | 12 | 20 |
| {Customers, Orders, Shipments} | Customers → Orders → Shipments | 960 | 12 | 20 |
| {Orders, Payments, Shipments} | Orders → Payments → Shipments | 960 | 12 | 23 |
| {Customers, Orders, Payments, Shipments} | Customers → Orders → Payments → Shipments | 960 | 15 | 37 |

Only connected subsets are retained. For example, {Customers, Payments} is not a valid standalone connected subset because there is no direct join predicate between those tables.

### 7.4 Selected Join Order

The optimizer selected:

```text
Customers
    JOIN Orders
        JOIN Payments
            JOIN Shipments
```

The corresponding left-deep plan is:

```text
JOIN
├── JOIN
│   ├── JOIN
│   │   ├── Customers
│   │   └── Orders
│   └── Payments
└── Shipments
```

The final estimated properties are:

| Property | Value |
|---|---:|
| Estimated output rows | 960 |
| Estimated output pages | 15 |
| Estimated I/O cost | 37 |

### 7.5 Analysis

The optimizer begins with Customers and Orders, producing an estimated intermediate result of 960 rows occupying eight pages.

Payments is added next, producing an estimated 960 rows occupying 12 pages.

Shipments is then joined to the intermediate result, producing an estimated 960 rows occupying 15 pages.

The DP algorithm compares connected expansions for each subset and retains the candidate with the lowest analytical I/O cost.

The selected complete plan has an estimated cost of 37 page-I/O operations.

This value is an analytical optimizer score, not a measurement of physical buffer reads.

The resulting plan is optimal within the candidates retained by the implemented left-deep dynamic programming algorithm and its analytical cost model. It is not necessarily the globally optimal physical execution plan.

The example also demonstrates deterministic tie-breaking: the optimizer consistently selects the same join order when candidate costs are equal.

### 7.6 Interpretation

This experiment confirms that the optimizer can:

- Enumerate connected subsets of a four-relation join graph.
- Retain estimated cardinalities, page counts, and costs.
- Construct a complete left-deep join plan.
- Select a deterministic minimum-cost candidate.
- Produce an inspectable DP table for analysis.

The demonstration validates the join-order search mechanism independently of the broader benchmark's measured execution improvements.

## 8. Correctness and Reproducibility

### 8.1 Result equivalence

The benchmark and regression tests compare baseline and optimized execution results.

The correlated-column regression tests additionally compare the complete row multisets of the original and corrected physical plans.

### 8.2 Deterministic datasets

Both benchmark datasets and the correlated-column dataset are generated using deterministic formulas.

This avoids dependence on random seeds or external data sources.

### 8.3 Self-contained regression tests

The correlated-column tests generate an isolated temporary database, collect statistics, and execute the relevant physical plans.

They do not require a manually created database to exist before pytest runs.

Seven dedicated correlation tests passed.

### 8.4 Final validation

The latest complete repository validation reported:

- 1,470 pytest tests passed.
- Ruff lint passed.
- Ruff formatting passed for 213 files.

These results verify the tested implementation and experiments, not unrestricted SQL support.

## 9. Threats to Validity

**Limited workload size:** The 20-query benchmark may not exercise every optimization opportunity.

**Small relations:** Buffer caching can hide improvements in logical work.

**Synthetic data:** Deterministic distributions are reproducible but may not represent production workloads.

**Analytical cost approximations:** The cost model does not capture all execution-level behavior.

**Restricted SQL support:** Some complex plans cannot be lowered into executable physical plans.

**Counterfactual correction:** The correlated experiment injects corrected cardinality information during planning. It does not implement a production multicolumn statistics estimator.

**Hardware and runtime effects:** The reported primary measurements are page-I/O counters, not wall-clock performance comparisons.

## 10. Conclusion

The Module 4 optimizer successfully integrates statistics-based planning, logical rewrites, dynamic programming join ordering, and cost-based physical algorithm selection with the existing database system.

The benchmark results demonstrate that projection pushdown provides the largest reduction in operator-level reads, particularly on the larger dataset.

Selection rewrites also reduce operator-level work, while projection cleanup and join ordering produce no measurable aggregate I/O improvement in the tested workload.

The cardinality evaluation identifies correlated predicates as a significant limitation of independent single-column statistics.

The separate correlated-column experiment demonstrates that a sufficiently large estimation error can change physical join selection and produce a measurable increase in buffer reads.

Overall, the results support the correctness and usefulness of the optimizer while clearly identifying limitations of the workload, statistical assumptions, and analytical cost model.