import pytest

from src.execution.limit import Limit
from src.execution.page_manager import SharedPageManager
from src.execution.seq_scan import SeqScan
from src.execution.union_all import UnionAll
from src.storage.catalog import Catalog
from src.storage.heap_file import HeapFile
from src.storage.record_codec import encode_record


def create_table(tmp_path, name, values):
    catalog = Catalog(tmp_path)
    metadata = catalog.create_table(name, "id:INT")

    heap = HeapFile(tmp_path / metadata.filename)

    for value in values:
        heap.insert(encode_record((value,), metadata.schema))

    heap.flush()


def collect(operator):
    rows = []

    while (row := operator.next()) is not None:
        rows.append(row)

    return rows


@pytest.mark.parametrize("count", [0, 1, 2, 10])
def test_limit_stops_pulling_child(tmp_path, count):
    create_table(tmp_path, "R", [1, 2, 3, 4])

    pages = SharedPageManager(frames=4)
    scan = SeqScan(tmp_path, "R", pages)
    limited = Limit(scan, count)

    limited.open()
    result = collect(limited)
    limited.close()

    expected = [(value,) for value in [1, 2, 3, 4][:count]]

    assert result == expected
    assert scan.counters()["tuples_out"] == len(expected)
    assert limited.counters()["tuples_out"] == len(expected)
    assert all(pin == 0 for pin in pages.pin_counts)


def test_union_all_preserves_duplicates(tmp_path):
    create_table(tmp_path, "R", [1, 2, 2])
    create_table(tmp_path, "S", [2, 3])

    pages = SharedPageManager(frames=4)

    left = SeqScan(tmp_path, "R", pages)
    right = SeqScan(tmp_path, "S", pages)
    union = UnionAll(left, right)

    union.open()
    result = collect(union)
    union.close()

    assert result == [
        (1,),
        (2,),
        (2,),
        (2,),
        (3,),
    ]

    assert union.schema == [("R.id", "INT")]
    assert left.counters()["tuples_out"] == 3
    assert right.counters()["tuples_out"] == 2
    assert union.counters()["tuples_out"] == 5
    assert all(pin == 0 for pin in pages.pin_counts)


def test_limit_over_union_all_stops_early(tmp_path):
    create_table(tmp_path, "R", [1, 2, 3])
    create_table(tmp_path, "S", [4, 5, 6])

    pages = SharedPageManager(frames=4)

    left = SeqScan(tmp_path, "R", pages)
    right = SeqScan(tmp_path, "S", pages)

    union = UnionAll(left, right)
    limited = Limit(union, 2)

    limited.open()
    result = collect(limited)
    limited.close()

    assert result == [(1,), (2,)]
    assert left.counters()["tuples_out"] == 2
    assert right.counters()["tuples_out"] == 0
    assert union.counters()["tuples_out"] == 2
    assert all(pin == 0 for pin in pages.pin_counts)
