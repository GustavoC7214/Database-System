
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import decode_record, encode_record


def test_catalog_codec_heap_integration(tmp_path):
    catalog = Catalog(tmp_path)

    catalog.create_table(
        "Students",
        "id:INT,name:VARCHAR(50),age:INT",
    )

    metadata = catalog.get_table("Students")
    heap = HeapFile(tmp_path / metadata.filename)

    records = [
        (1, "Alice", 20),
        (2, "Bob", 21),
        (3, "Café", 22),
    ]

    rids = []

    for record in records:
        encoded = encode_record(record, metadata.schema)
        rid = heap.insert(encoded)
        rids.append(rid)

    assert [
        decode_record(heap.get(rid), metadata.schema)
        for rid in rids
    ] == records

    metadata.page_count = heap.page_count
    metadata.tuple_count = len(records)
    catalog.update_table(metadata)

    heap.flush()

    reopened_catalog = Catalog(tmp_path)
    restored_metadata = reopened_catalog.get_table("Students")
    reopened_heap = HeapFile(tmp_path / restored_metadata.filename)

    assert restored_metadata.tuple_count == 3
    assert restored_metadata.page_count == heap.page_count

    restored_records = [
        decode_record(data, restored_metadata.schema)
        for _, data in reopened_heap.scan()
    ]

    assert restored_records == records
