"""Generate a deterministic database for correlated-column experiments."""

import argparse
from pathlib import Path

from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

DEFAULT_DB = Path("experiments/m4/results/correlated_db")

SCHEMAS = {
    "CorrelatedCustomers": "cid:INT,region:INT,tier:INT,age:INT",
    "CorrelatedOrders": "oid:INT,cid:INT,amount:INT,status:INT",
}


def generate_correlated_dataset(db_dir: Path) -> dict[str, int]:
    """Create two tables without overwriting an existing database."""
    if db_dir.exists():
        raise FileExistsError(f"Database already exists: {db_dir}")

    db_dir.mkdir(parents=True)
    catalog = Catalog(db_dir)

    customers = [
        (
            cid,
            (cid - 1) % 10 + 1,
            (cid - 1) % 10 + 1,
            18 + cid % 53,
        )
        for cid in range(1, 25_001)
    ]

    orders = [
        (
            oid,
            (oid - 1) % 25_000 + 1,
            20 + oid % 981,
            (oid - 1) % 4 + 1,
        )
        for oid in range(1, 6_001)
    ]

    tables = {
        "CorrelatedCustomers": customers,
        "CorrelatedOrders": orders,
    }

    counts = {}

    for name, rows in tables.items():
        metadata = catalog.create_table(name, SCHEMAS[name])
        heap = HeapFile(db_dir / metadata.filename)

        for row in rows:
            heap.insert(encode_record(row, metadata.schema))

        heap.flush()
        counts[name] = len(rows)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    counts = generate_correlated_dataset(args.db)

    for name, count in counts.items():
        print(f"{name}: {count} rows")

    print(f"Total: {sum(counts.values())} rows")


if __name__ == "__main__":
    main()
