"""Measure theoretical and actual slotted-page record capacity."""

from src.storage.record_codec import encode_record
from src.storage.slotted_page import SlottedPage

PAGE_SIZE = 4096
HEADER_SIZE = 8
SLOT_SIZE = 4

CASES = [
    ("INT", [("a", "INT")], (42,)),
    (
        "Mixed",
        [("a", "INT"), ("b", "VARCHAR(20)"), ("c", "INT")],
        (42, "bob", 7),
    ),
    (
        "Large VARCHAR",
        [("a", "INT"), ("b", "VARCHAR(100)")],
        (42, "x" * 100),
    ),
]


def main():
    for name, schema, values in CASES:
        record = encode_record(values, schema)
        record_size = len(record)

        theoretical = (PAGE_SIZE - HEADER_SIZE) // (record_size + SLOT_SIZE)

        page = SlottedPage(0)
        actual = 0

        while page.free_space >= record_size + SLOT_SIZE:
            page.insert(record)
            actual += 1

        print(
            f"{name}: "
            f"record_size={record_size}, "
            f"theoretical={theoretical}, "
            f"actual={actual}"
        )

        assert actual == theoretical


if __name__ == "__main__":
    main()
