
# Module 1 — Storage Engine and Buffer Pool Experimental Report

## 1. Introduction

This report evaluates the storage engine and buffer pool implemented for Project 2, Module 1.

The experiments examine three aspects of the implementation:

1. Record capacity within fixed-size slotted pages.
2. Buffer pool performance under LRU and CLOCK replacement policies.
3. Sequential scanning of a heap file containing 500 data pages.

All experiments use 4096-byte pages.

The benchmark scripts and raw measurements are stored in `experiments/m1/`.

## 2. Record Capacity Experiment

### 2.1 Methodology

The capacity experiment determines how many records can fit into a single slotted page.

Each page has:

- A fixed 8-byte header.
- A 4-byte slot entry for each record.
- Variable-length record data.

For a record of size `L` bytes, the theoretical maximum number of records is:

`floor((4096 - 8) / (L + 4))`

The experiment repeatedly inserts encoded records into a fresh slotted page until another insertion is no longer possible.

The measured capacity is compared against the theoretical calculation.

### 2.2 Results

| Schema | Example record | Record size | Theoretical capacity | Measured capacity |
|---|---|---:|---:|---:|
| `id:INT` | `(42,)` | 4 bytes | 511 | 511 |
| `id:INT,name:VARCHAR(20),age:INT` | `(42, "bob", 7)` | 13 bytes | 240 | 240 |
| `id:INT,text:VARCHAR(100)` | `(42, "x" * 100)` | 106 bytes | 37 | 37 |

### 2.3 Calculations

**Schema 1 — INT**

Each record occupies 4 bytes plus a 4-byte slot:

`floor(4088 / 8) = 511`

**Schema 2 — INT, VARCHAR(20), INT**

The example record occupies:

`4 + (2 + 3) + 4 = 13 bytes`

Including the slot:

`floor(4088 / 17) = 240`

**Schema 3 — INT, VARCHAR(100)**

The example record occupies:

`4 + (2 + 100) = 106 bytes`

Including the slot:

`floor(4088 / 110) = 37`

### 2.4 Analysis

The theoretical and measured capacities matched for all three schemas.

This confirms that the slotted-page implementation correctly accounts for the page header, slot directory, and encoded record lengths.

The results also demonstrate that VARCHAR storage depends on the actual UTF-8 byte length of each value rather than the declared maximum alone.

These capacities apply to the specific example records tested. Pages containing different VARCHAR lengths may have different capacities.

The capacity experiment is implemented in:

`experiments/m1/capacity.py`

## 3. Buffer Pool Replacement Policy Benchmarks

### 3.1 Methodology

The buffer pool was evaluated using five page-access traces and two replacement policies: LRU and CLOCK.

Each trace was replayed using buffer pool capacities of 4, 16, 64, and 256 frames.

This produced:

`5 traces × 4 frame capacities × 2 policies = 40 benchmark runs`

The experiments recorded:

- Cache hits and misses.
- Page evictions.
- Disk reads and writes.
- Cache hit rate.

The hit rate was calculated as:

`Hit rate (%) = 100 × hits / total accesses`

All benchmark traces were read-only, so no dirty pages were written to disk.

### 3.2 Workload Descriptions

| Trace | Accesses | Access pattern |
|---|---:|---|
| Sequential | 500 | Pages 0–499 accessed once |
| Looping | 512 | Pages 0–31 repeated 16 times |
| Hotset | 900 | Frequent accesses to pages 0–7, mixed with 40 other pages |
| Phased | 960 | Repeated accesses to pages 0–15, then 16–31, then 0–15 |
| Random | 1000 | Pseudorandom accesses to pages 0–127 using seed 42 |

### 3.3 Cache Hit Results

The following table compares cache hits for both policies.

| Trace | Frames | LRU hits | CLOCK hits |
|---|---:|---:|---:|
| Sequential | 4 | 0 | 0 |
| Sequential | 16 | 0 | 0 |
| Sequential | 64 | 0 | 0 |
| Sequential | 256 | 0 | 0 |
| Looping | 4 | 0 | 0 |
| Looping | 16 | 0 | 0 |
| Looping | 64 | 480 | 480 |
| Looping | 256 | 480 | 480 |
| Hotset | 4 | 0 | 0 |
| Hotset | 16 | 792 | 784 |
| Hotset | 64 | 852 | 852 |
| Hotset | 256 | 852 | 852 |
| Phased | 4 | 0 | 0 |
| Phased | 16 | 912 | 912 |
| Phased | 64 | 928 | 928 |
| Phased | 256 | 928 | 928 |
| Random | 4 | 40 | 39 |
| Random | 16 | 129 | 131 |
| Random | 64 | 481 | 487 |
| Random | 256 | 872 | 872 |

### 3.4 Replacement Policy Comparison

Across the 20 trace-and-capacity comparisons:

- LRU achieved more hits in 2 cases.
- CLOCK achieved more hits in 2 cases.
- Both policies tied in 16 cases.

The differences occurred in the following configurations:

| Trace | Frames | LRU hits | CLOCK hits | Better policy |
|---|---:|---:|---:|---|
| Hotset | 16 | 792 | 784 | LRU |
| Random | 4 | 40 | 39 | LRU |
| Random | 16 | 129 | 131 | CLOCK |
| Random | 64 | 481 | 487 | CLOCK |

Neither policy consistently outperformed the other.

### 3.5 Analysis by Workload

**Sequential workload**

Both policies recorded zero hits at every buffer capacity.

Each page was accessed only once, so increasing the buffer size could not create reuse.

**Looping workload**

The working set contained 32 pages.

With 4 or 16 frames, both policies experienced a cache miss on every access.

With 64 or 256 frames, all 32 pages fit in the buffer pool. Each page was loaded once, resulting in 480 hits and 32 misses.

**Hotset workload**

This trace repeatedly accessed eight frequently used pages alongside less frequent pages.

At 16 frames, LRU achieved 792 hits compared with 784 for CLOCK.

At 64 and 256 frames, both policies achieved 852 hits because the entire 48-page working set fit in memory.

**Phased workload**

This workload shifted between two groups of 16 pages.

At 16 frames, both policies achieved 912 hits.

At 64 and 256 frames, both groups fit in memory, producing 928 hits.

**Random workload**

The random trace accessed 128 possible pages.

At 4 frames, both policies achieved hit rates of approximately 4%.

At 16 frames, CLOCK achieved 131 hits compared with 129 for LRU.

At 64 frames, CLOCK achieved 487 hits compared with 481 for LRU.

At 256 frames, the entire working set fit in memory, resulting in 872 hits for both policies.

### 3.6 Conclusions

Buffer pool capacity and workload locality had a greater impact on performance than replacement policy selection.

Increasing the buffer size substantially improved hit rates when the working set could fit in memory.

For sequential accesses without page reuse, larger buffers did not improve hit rates.

LRU performed slightly better in the 16-frame hotset experiment, while CLOCK performed slightly better in some random-access configurations.

The results do not establish either policy as universally superior.

The benchmark implementation and complete statistics are available in:

- `experiments/m1/run_benchmarks.py`
- `experiments/m1/results/buffer_benchmarks.csv`

## 4. Sequential Scan Experiment

### 4.1 Methodology

This experiment evaluates the buffer pool while scanning a heap file containing 500 data pages.

Each data page contains one record occupying 4084 bytes, allowing exactly one record per page.

The heap also contains one directory page, giving a total of 501 pages.

The experiment creates and flushes the heap file, then reopens it for scanning.

Both LRU and CLOCK replacement policies are tested with buffer pool capacities of 2, 8, and 64 frames.

Statistics collected during heap initialization are excluded from the scan measurements.

### 4.2 Results

| Policy | Frames | Records | Hits | Misses | Evictions | Reads | Writes |
|---|---:|---:|---:|---:|---:|---:|---:|
| LRU | 2 | 500 | 1 | 500 | 499 | 500 | 0 |
| LRU | 8 | 500 | 1 | 500 | 493 | 500 | 0 |
| LRU | 64 | 500 | 1 | 500 | 437 | 500 | 0 |
| CLOCK | 2 | 500 | 1 | 500 | 499 | 500 | 0 |
| CLOCK | 8 | 500 | 1 | 500 | 493 | 500 | 0 |
| CLOCK | 64 | 500 | 1 | 500 | 437 | 500 | 0 |

### 4.3 Analysis

All six configurations successfully scanned 500 records.

Each of the 500 data pages was accessed once, producing 500 cache misses and 500 disk reads.

The single cache hit occurred because the heap directory page was already cached during initialization.

Increasing the buffer capacity reduced the number of evictions:

- 2 frames: 499 evictions.
- 8 frames: 493 evictions.
- 64 frames: 437 evictions.

However, larger buffers did not reduce the number of disk reads because each data page was accessed only once.

LRU and CLOCK produced identical results for all three buffer capacities.

No disk writes occurred during the measured scan because the operation was read-only.

### 4.4 Conclusion

The experiment demonstrates that the heap file can scan records across hundreds of data pages while using a small fixed-size buffer pool.

The scan completed successfully with only two buffer frames.

For a one-pass sequential scan, increasing buffer capacity reduces evictions but does not improve the cache hit rate when data pages are not revisited.

The experiment and raw results are available in:

- `experiments/m1/sequential_scan.py`
- `experiments/m1/results/sequential_scan.csv`

## 5. Testing and Validation

The storage engine was validated using automated tests covering:

- Disk page allocation, reading, and writing.
- Slotted-page insertion, retrieval, and deletion.
- Directory-page metadata and linked directory pages.
- Heap-file insertion, scanning, and record identifiers.
- Record encoding and decoding.
- Schema validation and catalog persistence.
- CSV loading and error handling.
- Buffer pool pinning, eviction, and dirty-page flushing.
- LRU and CLOCK replacement policies.
- Storage CLI commands and trace replay.
- Integration between storage components.

The full regression suite passed with 485 tests.

Static analysis using Ruff also completed successfully without reported errors.

These checks were performed before the final documentation stage. They will be repeated before submission.

## 6. Overall Conclusions

The experiments demonstrate that the Module 1 storage engine supports fixed-size disk pages, variable-length records, heap-file organization, and buffer pool management.

The record-capacity experiment confirmed that measured page capacities matched theoretical calculations for all three tested schemas.

The buffer pool benchmarks showed that replacement policy performance depends on the workload. LRU and CLOCK tied in 16 of 20 comparisons, with small differences in the remaining configurations.

Buffer capacity and page-access locality had a greater influence on cache performance than the replacement policy itself.

The sequential scan experiment confirmed that a heap containing 500 data pages could be scanned successfully with as few as two buffer frames.

Overall, the implementation provides a functional storage foundation for subsequent database-system modules.

## 7. Reproducing the Experiments

From the project root, run:

```bash
python3 experiments/m1/capacity.py
python3 experiments/m1/run_benchmarks.py
python3 experiments/m1/sequential_scan.py
```

The buffer pool and sequential scan measurements are saved to:

- `experiments/m1/results/buffer_benchmarks.csv`
- `experiments/m1/results/sequential_scan.csv`

The generated results can be compared with the measurements presented in this report.
