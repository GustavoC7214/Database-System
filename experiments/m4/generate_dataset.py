"""Generate deterministic disk-backed Module 4 benchmark databases.

The dataset and workload are student-defined because the referenced
assignment files were not supplied.
"""

import argparse
import shutil
from pathlib import Path

from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record

DEFAULT_DB = Path("experiments/m4/results/benchmark_db")

SCHEMAS = {
    "Customers": "cid:INT,region:INT,tier:INT,age:INT",
    "Orders": "oid:INT,cid:INT,amount:INT,status:INT",
    "Payments": "pid:INT,oid:INT,method:INT,amount:INT",
    "Shipments": "sid:INT,oid:INT,warehouse:INT,days:INT",
}

BASE_CUSTOMERS = 240
ORDERS_PER_CUSTOMER = 4


def generate_customers(
    scale: int = 1,
) -> list[tuple[int, ...]]:
    """Generate customers with correlated region and tier."""
    if scale < 1:
        raise ValueError("Scale must be at least 1")

    rows = []

    for cid in range(1, BASE_CUSTOMERS * scale + 1):
        region = (cid - 1) % 4 + 1

        # Preserve the original 90% region/tier correlation.
        tier = region if cid % 10 != 0 else region % 4 + 1

        age = 18 + (cid * 7) % 53
        rows.append((cid, region, tier, age))

    return rows


def generate_orders(
    scale: int = 1,
) -> list[tuple[int, ...]]:
    """Generate four orders per customer."""
    if scale < 1:
        raise ValueError("Scale must be at least 1")

    customer_count = BASE_CUSTOMERS * scale
    order_count = customer_count * ORDERS_PER_CUSTOMER
    rows = []

    for oid in range(1, order_count + 1):
        cid = (oid - 1) % customer_count + 1
        amount = 20 + (oid * 37) % 981
        status = (oid - 1) % 4 + 1

        rows.append((oid, cid, amount, status))

    return rows


def generate_payments(
    scale: int = 1,
) -> list[tuple[int, ...]]:
    """Generate exactly one payment per order."""
    if scale < 1:
        raise ValueError("Scale must be at least 1")

    order_count = BASE_CUSTOMERS * scale * ORDERS_PER_CUSTOMER
    rows = []

    for pid in range(1, order_count + 1):
        oid = pid
        method = (pid * 3) % 4 + 1
        amount = 20 + (oid * 37) % 981

        rows.append((pid, oid, method, amount))

    return rows


def generate_shipments(
    scale: int = 1,
) -> list[tuple[int, ...]]:
    """Generate exactly one shipment per order."""
    if scale < 1:
        raise ValueError("Scale must be at least 1")

    order_count = BASE_CUSTOMERS * scale * ORDERS_PER_CUSTOMER
    rows = []

    for sid in range(1, order_count + 1):
        oid = sid
        warehouse = (sid - 1) % 4 + 1
        days = 1 + (sid * 7) % 14

        rows.append((sid, oid, warehouse, days))

    return rows


def generate_dataset(
    db_dir: Path,
    *,
    scale: int = 1,
    overwrite: bool = False,
) -> dict[str, int]:
    """Create the database and return its table cardinalities."""
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise TypeError("Scale must be an integer")
    if scale < 1:
        raise ValueError("Scale must be at least 1")

    db_dir = db_dir.resolve()

    if db_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{db_dir} already exists. Use --overwrite to replace it."
            )
        if not db_dir.is_dir() or db_dir.is_symlink():
            raise ValueError("Database path must be a regular directory")
        shutil.rmtree(db_dir)

    db_dir.mkdir(parents=True)
    catalog = Catalog(db_dir)

    tables = {
        "Customers": generate_customers(scale),
        "Orders": generate_orders(scale),
        "Payments": generate_payments(scale),
        "Shipments": generate_shipments(scale),
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
    parser = argparse.ArgumentParser(
        description="Generate the Module 4 benchmark database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        help="Dataset size multiplier (default: 1)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()
    counts = generate_dataset(
        args.db,
        scale=args.scale,
        overwrite=args.overwrite,
    )

    print(f"Database: {args.db.resolve()}")
    print(f"Scale: {args.scale}x")

    for name, count in counts.items():
        print(f"{name}: {count} rows")

    print(f"Total: {sum(counts.values())} rows")


if __name__ == "__main__":
    main()
