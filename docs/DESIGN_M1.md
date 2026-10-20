
# Module 1 — Storage Engine and Buffer Pool Design

## 1. Overview

Module 1 implements persistent, page-based storage for the database system.

The storage engine is organized into the following components:

- **DiskManager:** Reads, writes, and allocates fixed-size disk pages.
- **SlottedPage:** Stores variable-length records within a data page.
- **DirectoryPage:** Tracks data-page locations and available space.
- **HeapFile:** Coordinates record insertion, retrieval, deletion, and scanning.
- **BufferPool:** Caches disk pages using LRU or CLOCK replacement.
- **RecordCodec:** Encodes and decodes typed records.
- **Schema:** Parses and validates table definitions.
- **Catalog:** Maintains persistent table metadata.
- **CSVLoader:** Loads records from CSV files.
- **Storage CLI:** Provides commands for managing and inspecting stored tables.

The storage layer uses 4096-byte pages and little-endian binary encoding.

## 2. Disk Page Organization

Each table is stored in a separate heap file.

Page IDs are zero-based, and the byte offset of a page is:

`page_offset = page_id * 4096`

Page 0 is the first heap-directory page. Additional directory pages are linked when necessary.

Data pages contain slotted records and are registered in the heap directory.

## 3. Slotted Data Page

Each slotted page occupies exactly 4096 bytes.

### 3.1 Header Layout

| Byte offset | Size | Field | Description |
|---|---|---|---|
| 0 | 4 | page_id | Unsigned 32-bit page identifier |
| 4 | 2 | slot_count | Number of allocated slots, including deleted slots |
| 6 | 2 | free_end | Beginning of the stored record-data region |

All integer fields use little-endian encoding.

The header occupies 8 bytes.

### 3.2 Slot Directory

The slot directory begins at byte offset 8.

Each slot occupies 4 bytes:

| Relative offset | Size | Field |
|---|---|---|
| 0 | 2 | record_offset |
| 2 | 2 | record_length |

Slot `i` begins at:

`8 + 4 * i`

Slots grow forward from the beginning of the page.

Record data grows backward from the end of the page.

### 3.3 Free-Space Calculation

Available contiguous space is calculated as:

`free_space = free_end - (8 + 4 * slot_count)`

A new record of length `L` requires:

`L + 4` bytes

The additional four bytes are needed for its slot entry.

An empty slotted page has:

`4096 - 8 = 4088` free bytes.

The maximum record length is:

`4096 - 8 - 4 = 4084` bytes.

### 3.4 Record Insertion

Insertion follows these steps:

1. Validate that the record does not exceed 4084 bytes.
2. Check that enough free space exists for the record and its slot.
3. Decrease `free_end` by the record length.
4. Copy the record bytes into the new data region.
5. Append a slot containing the record offset and length.
6. Increment `slot_count`.
7. Return the new slot number.

If the record is valid but insufficient space remains, insertion returns `None`.

### 3.5 Record Identifiers

Each stored record is identified by:

`RID = (page_id, slot_no)`

Both components are zero-based.

The page ID identifies the data page, and the slot number identifies the record within that page.

### 3.6 Record Deletion

Deleting a record changes its slot entry to:

`(record_offset, record_length) = (0, 0)`

Deleted slots are not reused.

The implementation does not compact record data or reclaim deleted space.

Consequently, `slot_count` includes both live and deleted records, and deletion does not increase the page's reported free space.

## 4. Heap Directory Page

Directory pages track the data pages belonging to a heap file.

Each directory page occupies 4096 bytes.

### 4.1 Header Layout

| Byte offset | Size | Field | Description |
|---|---|---|---|
| 0 | 4 | page_id | Directory page identifier |
| 4 | 4 | next_dir_page | Next directory page ID |
| 8 | 2 | entry_count | Number of directory entries |

The header occupies 10 bytes.

The value `0xFFFFFFFF` indicates that no next directory page exists.

### 4.2 Directory Entries

Directory entries begin at byte offset 10.

Each entry occupies 6 bytes:

| Relative offset | Size | Field |
|---|---|---|
| 0 | 4 | data_page_id |
| 4 | 2 | free_bytes |

The maximum number of entries per directory page is:

`floor((4096 - 10) / 6) = 681`

Each entry identifies a data page and its currently recorded free space.

### 4.3 Directory Chaining

The first directory is stored at page 0.

When a directory becomes full and another data page is needed, the heap file allocates a new directory page.

The previous directory's `next_dir_page` field is updated to point to the new directory.

The final directory uses `0xFFFFFFFF` as its next-page marker.

### 4.4 Heap Insertion Strategy

The heap uses first-fit insertion.

It examines directory entries in order and selects the first data page with sufficient recorded free space.

After inserting the record, the directory entry is updated with the page's new free-space value.

If no existing data page has sufficient space, a new data page is allocated and registered in the directory.

### 4.5 Heap Scanning

The heap scan visits directory pages in chain order.

For each registered data page, it examines the page's slots and yields only live records.

Deleted slots are skipped.

The scan yields pairs in the form:

`(RID, record_bytes)`

The scan is implemented as a generator, allowing records to be consumed lazily.

## 5. Record Encoding

Records are encoded according to their table schema.

The implementation supports two data types: `INT` and `VARCHAR(n)`.

### 5.1 INT Encoding

An `INT` occupies exactly 4 bytes.

It is encoded as a signed 32-bit little-endian integer.

Supported range:

`-2147483648` to `2147483647`

Values outside this range are rejected. Boolean values are not accepted as integers.

### 5.2 VARCHAR Encoding

A `VARCHAR(n)` field consists of:

1. A 2-byte unsigned little-endian length prefix.
2. The UTF-8 encoded string bytes.

The length prefix stores the number of UTF-8 bytes, not the number of Unicode characters.

The schema parameter `n` must be between 1 and 255.

The encoded string must contain no more than `n` UTF-8 bytes.

For a string containing `L` UTF-8 bytes, the field occupies:

`2 + L` bytes.

### 5.3 Complete Record Layout

A record is formed by concatenating its encoded fields in schema order.

There is no record-level header, NULL bitmap, or alignment padding.

For example, consider the schema:

`id:INT,name:VARCHAR(20),age:INT`

The record:

`(42, "bob", 7)`

is encoded as:

| Field | Encoding | Size |
|---|---|---:|
| id | Signed little-endian INT | 4 bytes |
| name length | Unsigned little-endian length = 3 | 2 bytes |
| name | UTF-8 bytes for "bob" | 3 bytes |
| age | Signed little-endian INT | 4 bytes |
| **Total** | | **13 bytes** |

The record decoder uses the schema to determine field boundaries.

It rejects truncated fields, invalid field lengths, unsupported types, and unexpected trailing bytes.

## 6. Schema Definition and Validation

Schemas are specified as comma-separated column definitions.

Each column uses the format:

`column_name:TYPE`

For example:

`id:INT,name:VARCHAR(20),age:INT`

Supported types are:

- `INT`
- `VARCHAR(n)`, where `1 <= n <= 255`

Column names must begin with an ASCII letter or underscore.

Subsequent characters may contain ASCII letters, digits, or underscores.

Duplicate column names are rejected.

Column types are normalized to uppercase.

The parser returns an ordered list of `(column_name, column_type)` pairs.

Preserving column order is important because records are encoded and decoded according to that order.

### 6.1 Validation

The implementation rejects:

- Empty schemas.
- Missing column names or types.
- Invalid column identifiers.
- Duplicate column names.
- Unsupported data types.
- VARCHAR declarations outside the supported length range.
- Record values that do not match their declared types.
- Records with the wrong number of fields.

## 7. Buffer Pool

The buffer pool caches disk pages in a fixed number of memory frames.

Its capacity is specified when the buffer pool is created. The implementation requires at least one frame.

Two replacement policies are supported:

- Least Recently Used (LRU)
- CLOCK

### 7.1 Buffer Frames

Each buffer frame stores:

| Field | Purpose |
|---|---|
| page_id | Identifies the cached page |
| data | Contains the 4096-byte page |
| pin_count | Counts active users of the page |
| dirty | Indicates whether the page has been modified |
| reference_bit | Records recent use for CLOCK |
| last_access | Records access order for LRU |

A page table maps disk page IDs to buffer-frame indices.

### 7.2 Page Fetching

When a page is requested, the buffer pool first checks its page table.

If the page is already cached:

1. Increment the hit counter.
2. Increment the frame's pin count.
3. Update its access timestamp.
4. Set its CLOCK reference bit.
5. Return the cached page data.

If the page is not cached:

1. Read the page from disk.
2. Select an available frame or replacement victim.
3. Write back the existing page if the victim is dirty.
4. Remove the evicted page from the page table.
5. Install the requested page in the selected frame.
6. Set its pin count to 1.
7. Update its replacement metadata.
8. Increment the miss and read counters.

The buffer pool never replaces a pinned page.

If every frame is pinned and another frame is required, the operation raises a runtime error.

### 7.3 Pinning and Unpinning

Fetching a page increments its pin count.

Callers must unpin pages when they finish using them.

Unpinning decreases the pin count by one.

The caller may also indicate that the page was modified.

Dirty status is preserved until the modified page is written to disk.

Attempting to unpin a page that is not cached, or one whose pin count is already zero, raises an error.

### 7.4 LRU Replacement

LRU replaces the least recently accessed unpinned page.

Each successful page access receives an increasing access counter.

The counter is stored in the frame's `last_access` field.

When replacement is required, the buffer pool selects the unpinned frame with the smallest `last_access` value.

Unused frames are selected before occupied frames.

### 7.5 CLOCK Replacement

CLOCK maintains a circular pointer called the clock hand.

Each cached page has a reference bit.

A page access sets its reference bit to true.

During replacement:

1. Skip pinned frames.
2. If an unpinned frame has its reference bit set, clear the bit and continue.
3. Select the first unpinned frame whose reference bit is clear.

The clock hand advances as frames are examined.

Unused frames are selected before occupied frames.

CLOCK approximates recent-use behaviour without maintaining a full access ordering for every replacement decision.

### 7.6 Dirty Pages and Flushing

Modified pages are marked dirty.

When a dirty page is evicted, its contents are written to disk before the frame is reused.

The `flush_all()` operation writes every dirty cached page to disk and clears its dirty flag.

Clean pages do not require write-back during eviction.

### 7.7 New Page Allocation

The `new_page()` operation allocates a new disk page and installs it into a buffer frame.

The new frame is initialized with zero-filled data, pinned once, and marked dirty.

If an occupied frame must be replaced, normal eviction and dirty-page write-back rules apply.

Allocating a new page does not count as a page-read miss.

### 7.8 Buffer Pool Statistics

The buffer pool maintains five counters:

| Counter | Meaning |
|---|---|
| hits | Requests satisfied by an already cached page |
| misses | Requests requiring a disk-page read |
| evictions | Cached pages removed to make room |
| reads | Page reads performed through the buffer pool |
| writes | Dirty-page writes caused by eviction or flushing |

The counters can be retrieved using `stats()`.

For a trace with `H` hits and `M` misses, the hit rate is:

`hit_rate = H / (H + M)`

The experimental comparison of LRU and CLOCK is documented in `REPORT_M1.md`.

## 8. Catalog and Table Metadata

The catalog maintains persistent metadata describing the tables stored in the database.

It is implemented using the same heap-file storage system as ordinary tables.

The catalog is stored in:

`catalog.db`

Each user table is stored in a separate file named:

`<table_name>.db`

### 8.1 Table Metadata

Each table has a `TableMetadata` record containing:

| Field | Description |
|---|---|
| name | Logical table name |
| filename | Name of the table's heap file |
| schema | Ordered list of column names and types |
| page_count | Number of pages in the table's heap file |
| tuple_count | Number of tuples recorded for the table |

When a table is first created, its heap file contains an initial directory page.

Therefore, its initial page count is 1 and its tuple count is 0.

### 8.2 Metadata Encoding

Table metadata is serialized as UTF-8 JSON.

The JSON object contains the table name, filename, schema, page count, and tuple count.

The serialized JSON bytes are stored as records inside the catalog heap file.

When metadata is retrieved, the JSON is decoded into a `TableMetadata` object.

### 8.3 Table Creation

Creating a table follows these steps:

1. Validate the table name.
2. Reject the reserved name `catalog`.
3. Check that the table is not already registered.
4. Parse and validate the supplied schema.
5. Check that the target table file does not already exist.
6. Create a new heap file for the table.
7. Construct the initial table metadata.
8. Insert the metadata record into the catalog.
9. Flush the catalog to disk.

Table names must be valid ASCII Python identifiers.

### 8.4 Catalog Operations

The catalog provides the following operations:

- `create_table()` creates a table and registers its metadata.
- `get_table()` retrieves metadata by table name.
- `list_tables()` returns registered table names.
- `update_table()` replaces an existing metadata record.
- `flush()` persists dirty catalog pages.

Catalog lookup and table listing use heap scans.

### 8.5 Metadata Updates

Updating table metadata follows an insert-before-delete strategy.

The catalog first inserts the replacement metadata record.

It then marks the previous metadata record as deleted and flushes the heap file.

This avoids deleting the existing record before space for the replacement has been allocated.

The catalog uses the slotted-page deletion policy, so deleted metadata slots are not reused and their record space is not reclaimed.

## 9. CSV Loading and Error Handling

The CSV loader imports records from a CSV file into an existing table.

The loader uses the table schema stored in the catalog to convert text fields into typed values.

### 9.1 Input Format

CSV files are expected to be headerless.

Each CSV row represents one record, with fields appearing in the same order as the table schema.

The implementation uses Python's standard `csv` module with strict parsing enabled.

This supports standard CSV quoting, including quoted fields containing commas and newlines.

Files are read using UTF-8 encoding.

### 9.2 Row Validation

For each CSV row, the loader:

1. Checks that the number of fields matches the table schema.
2. Converts INT fields from text to integers.
3. Validates that integers fit within the signed 32-bit range.
4. Checks VARCHAR values against their maximum UTF-8 byte lengths.
5. Encodes the validated values into a binary record.
6. Inserts the record into the table's heap file.

An invalid row produces a descriptive error rather than silently inserting incorrect data.

### 9.3 Error Reporting

Validation errors identify the table, CSV row number, and column number when applicable.

Column errors also include the column name.

Examples of rejected input include:

- Too many or too few columns.
- Text that cannot be converted to an INT.
- An INT outside the signed 32-bit range.
- A VARCHAR value exceeding its declared byte length.
- A record too large to fit into a slotted page.
- Malformed CSV quoting.

For malformed CSV syntax, the loader reports the physical file line number provided by the CSV reader. The column is reported as unknown.

For ordinary row validation, the reported row number is the CSV record number.

These numbers can differ when a quoted CSV field contains embedded newlines.

### 9.4 Persistence and Metadata Updates

The loader tracks how many records have been inserted successfully.

After loading, it updates:

- The table's page count.
- The table's tuple count.

The heap file is flushed, and the updated metadata is stored in the catalog.

### 9.5 Partial Loading Behaviour

CSV loading is not implemented as an atomic transaction.

If a later row is invalid, previously inserted records are retained.

The loader's `finally` block flushes the heap and updates the catalog using the number of successfully inserted records.

This ensures that persisted table metadata reflects successful insertions even when the overall load operation raises an error.

The loader does not roll back records inserted before the error.

## 10. Storage Command-Line Interface

The storage engine provides a command-line interface implemented in `src/storage/cli.py`.

Commands are executed from the project root using:

`python3 -m src.storage.cli <command> [options]`

The interface uses Python's standard `argparse` module.

### 10.1 Create Table

The `create-table` command creates a heap file and registers the table in the catalog.

Example:

```bash
python3 -m src.storage.cli create-table \
  --db data \
  --name students \
  --schema "id:INT,name:VARCHAR(50)"
```

Required arguments:

- `--db`: Database directory.
- `--name`: Table name.
- `--schema`: Comma-separated column definitions.

The command prints the created table name, schema, and filename.

### 10.2 Load CSV

The `load` command imports a headerless CSV file into an existing table.

Example:

```bash
python3 -m src.storage.cli load \
  --db data \
  --table students \
  --file students.csv
```

Required arguments:

- `--db`: Database directory.
- `--table`: Existing table name.
- `--file`: CSV file path.

The command prints the number of successfully loaded records when loading completes.

### 10.3 Scan Table

The `scan` command reads stored records and decodes them using the table schema.

Example:

```bash
python3 -m src.storage.cli scan \
  --db data \
  --table students \
  --frames 8 \
  --limit 10 \
  --json
```

Arguments:

- `--db`: Database directory.
- `--table`: Existing table name.
- `--frames`: Buffer pool size, default 8.
- `--limit`: Maximum number of records to display.
- `--json`: Output records as JSON.

Without `--json`, each record is printed as a Python dictionary.

A limit of zero displays no records.

### 10.4 Inspect Page Layout

The `layout` command displays the internal structure of a registered data page.

Example:

```bash
python3 -m src.storage.cli layout \
  --db data \
  --table students \
  --page 1
```

Required arguments:

- `--db`: Database directory.
- `--table`: Existing table name.
- `--page`: Zero-based data page ID.

The command displays:

- Page ID.
- Slot count.
- Free-space boundary.
- Available free space.
- Record offsets and lengths.
- Deleted slot markers.

The command verifies that the requested page belongs to the table's directory entries.

Directory pages and unregistered pages cannot be inspected as data pages.

### 10.5 Replay Buffer Pool Trace

The `trace` command replays page accesses through a configurable buffer pool.

Example:

```bash
python3 -m src.storage.cli trace \
  --db data \
  --file experiments/m1/traces/hotset.txt \
  --frames 16 \
  --policy clock \
  --json
```

Arguments:

- `--db`: Database directory.
- `--file`: Page-access trace file.
- `--frames`: Buffer pool size, default 16.
- `--policy`: `lru` or `clock`, default `lru`.
- `--json`: Output statistics as JSON.

The command reports:

- Cache hits.
- Cache misses.
- Evictions.
- Disk reads.
- Disk writes.

### 10.6 Command-Line Validation

The CLI validates buffer frame counts and scan limits.

Frame counts must be at least 1.

Scan limits cannot be negative.

The `layout` command checks page bounds and verifies that the page is registered as a data page.

Invalid command-line arguments are reported using `argparse` errors.
