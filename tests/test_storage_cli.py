
import json

import pytest

from src.storage.catalog import Catalog
from src.storage.cli import main
from src.storage.heap_file import HeapFile
from src.storage.record_codec import decode_record


def test_create_table_command(tmp_path, capsys):
    result = main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Students",
        "--schema", "id:INT,name:VARCHAR(50),age:INT",
    ])

    assert result == 0
    assert (tmp_path / "catalog.db").exists()
    assert (tmp_path / "Students.db").exists()

    metadata = Catalog(tmp_path).get_table("Students")

    assert metadata.name == "Students"
    assert metadata.filename == "Students.db"
    assert metadata.schema == [
        ("id", "INT"),
        ("name", "VARCHAR(50)"),
        ("age", "INT"),
    ]
    assert metadata.tuple_count == 0

    output = capsys.readouterr().out
    assert "Created table: Students" in output


def test_create_table_rejects_duplicate(tmp_path):
    arguments = [
        "create-table",
        "--db", str(tmp_path),
        "--name", "Students",
        "--schema", "id:INT",
    ]

    assert main(arguments) == 0

    with pytest.raises(ValueError, match="Table already exists"):
        main(arguments)


def test_create_table_rejects_invalid_schema(tmp_path):
    with pytest.raises(ValueError):
        main([
            "create-table",
            "--db", str(tmp_path),
            "--name", "Students",
            "--schema", "id:FLOAT",
        ])

    assert not (tmp_path / "Students.db").exists()


def test_create_table_requires_arguments():
    with pytest.raises(SystemExit) as exc:
        main([
            "create-table",
            "--db", "my_database",
        ])

    assert exc.value.code == 2


def test_load_command(tmp_path, capsys):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Students",
        "--schema", "id:INT,name:VARCHAR(50),age:INT",
    ])

    csv_path = tmp_path / "students.csv"
    csv_path.write_text(
        "1,Alice,20\n2,Bob,21\n",
        encoding="utf-8",
    )

    result = main([
        "load",
        "--db", str(tmp_path),
        "--table", "Students",
        "--file", str(csv_path),
    ])

    assert result == 0

    metadata = Catalog(tmp_path).get_table("Students")
    assert metadata.tuple_count == 2

    heap = HeapFile(tmp_path / metadata.filename)
    records = [
        decode_record(data, metadata.schema)
        for _, data in heap.scan()
    ]

    assert records == [
        (1, "Alice", 20),
        (2, "Bob", 21),
    ]

    output = capsys.readouterr().out
    assert "Loaded 2 records into table Students" in output


def test_load_command_with_quoted_csv(tmp_path):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "People",
        "--schema", "id:INT,name:VARCHAR(50)",
    ])

    csv_path = tmp_path / "people.csv"
    csv_path.write_text(
        '1,"Smith, John"\n2,Café\n',
        encoding="utf-8",
    )

    assert main([
        "load",
        "--db", str(tmp_path),
        "--table", "People",
        "--file", str(csv_path),
    ]) == 0

    metadata = Catalog(tmp_path).get_table("People")
    heap = HeapFile(tmp_path / metadata.filename)

    records = [
        decode_record(data, metadata.schema)
        for _, data in heap.scan()
    ]

    assert records == [
        (1, "Smith, John"),
        (2, "Café"),
    ]


def test_load_command_rejects_missing_table(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Table does not exist"):
        main([
            "load",
            "--db", str(tmp_path),
            "--table", "Missing",
            "--file", str(csv_path),
        ])


def test_load_command_requires_arguments():
    with pytest.raises(SystemExit) as exc:
        main([
            "load",
            "--db", "my_database",
        ])

    assert exc.value.code == 2


def test_scan_command_json(tmp_path, capsys):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Students",
        "--schema", "id:INT,name:VARCHAR(50)",
    ])

    csv_path = tmp_path / "students.csv"
    csv_path.write_text(
        "1,Alice\n2,Bob\n3,Café\n",
        encoding="utf-8",
    )

    main([
        "load",
        "--db", str(tmp_path),
        "--table", "Students",
        "--file", str(csv_path),
    ])

    capsys.readouterr()

    result = main([
        "scan",
        "--db", str(tmp_path),
        "--table", "Students",
        "--frames", "2",
        "--json",
    ])

    assert result == 0

    records = json.loads(capsys.readouterr().out)

    assert records == [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Café"},
    ]


def test_scan_command_limit(tmp_path, capsys):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Numbers",
        "--schema", "value:INT",
    ])

    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text(
        "10\n20\n30\n",
        encoding="utf-8",
    )

    main([
        "load",
        "--db", str(tmp_path),
        "--table", "Numbers",
        "--file", str(csv_path),
    ])

    capsys.readouterr()

    main([
        "scan",
        "--db", str(tmp_path),
        "--table", "Numbers",
        "--limit", "2",
        "--json",
    ])

    assert json.loads(capsys.readouterr().out) == [
        {"value": 10},
        {"value": 20},
    ]


def test_scan_command_zero_limit(tmp_path, capsys):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Numbers",
        "--schema", "value:INT",
    ])

    capsys.readouterr()

    main([
        "scan",
        "--db", str(tmp_path),
        "--table", "Numbers",
        "--limit", "0",
        "--json",
    ])

    assert json.loads(capsys.readouterr().out) == []


def test_scan_command_rejects_invalid_frames(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main([
            "scan",
            "--db", str(tmp_path),
            "--table", "Numbers",
            "--frames", "0",
        ])

    assert exc.value.code == 2


def test_scan_command_rejects_negative_limit(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main([
            "scan",
            "--db", str(tmp_path),
            "--table", "Numbers",
            "--limit", "-1",
        ])

    assert exc.value.code == 2


def test_layout_command(tmp_path, capsys):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Numbers",
        "--schema", "value:INT",
    ])

    csv_path = tmp_path / "numbers.csv"
    csv_path.write_text("10\n20\n", encoding="utf-8")

    main([
        "load",
        "--db", str(tmp_path),
        "--table", "Numbers",
        "--file", str(csv_path),
    ])

    capsys.readouterr()

    result = main([
        "layout",
        "--db", str(tmp_path),
        "--table", "Numbers",
        "--page", "1",
    ])

    assert result == 0

    output = capsys.readouterr().out

    assert "Table: Numbers" in output
    assert "Page ID: 1" in output
    assert "Slot count: 2" in output
    assert "Free end: 4088" in output
    assert "Free space: 4072" in output
    assert "Slot 0: offset=4092, length=4" in output
    assert "Slot 1: offset=4088, length=4" in output


def test_layout_command_rejects_directory_page(tmp_path):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Numbers",
        "--schema", "value:INT",
    ])

    with pytest.raises(SystemExit) as exc:
        main([
            "layout",
            "--db", str(tmp_path),
            "--table", "Numbers",
            "--page", "0",
        ])

    assert exc.value.code == 2


def test_layout_command_rejects_nonexistent_page(tmp_path):
    main([
        "create-table",
        "--db", str(tmp_path),
        "--name", "Numbers",
        "--schema", "value:INT",
    ])

    with pytest.raises(SystemExit) as exc:
        main([
            "layout",
            "--db", str(tmp_path),
            "--table", "Numbers",
            "--page", "99",
        ])

    assert exc.value.code == 2


def test_trace_command_lru_json(tmp_path, capsys):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    result = main([
        "trace",
        "--db", str(tmp_path),
        "--file", str(trace_path),
        "--frames", "3",
        "--policy", "lru",
        "--json",
    ])

    assert result == 0

    stats = json.loads(capsys.readouterr().out)

    assert stats == {
        "hits": 1,
        "misses": 5,
        "evictions": 2,
        "reads": 5,
        "writes": 0,
    }


def test_trace_command_clock_json(tmp_path, capsys):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "1\n2\n3\n1\n4\n2\n",
        encoding="utf-8",
    )

    result = main([
        "trace",
        "--db", str(tmp_path),
        "--file", str(trace_path),
        "--frames", "3",
        "--policy", "clock",
        "--json",
    ])

    assert result == 0

    stats = json.loads(capsys.readouterr().out)

    assert stats == {
        "hits": 2,
        "misses": 4,
        "evictions": 1,
        "reads": 4,
        "writes": 0,
    }


def test_trace_command_text_output(tmp_path, capsys):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("1\n1\n2\n", encoding="utf-8")

    result = main([
        "trace",
        "--db", str(tmp_path),
        "--file", str(trace_path),
        "--frames", "2",
        "--policy", "lru",
    ])

    assert result == 0

    output = capsys.readouterr().out

    assert "Replacement policy: LRU" in output
    assert "Buffer frames: 2" in output
    assert "Hits: 1" in output
    assert "Misses: 2" in output
    assert "Evictions: 0" in output
    assert "Disk reads: 2" in output
    assert "Disk writes: 0" in output


def test_trace_command_rejects_zero_frames(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text("1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main([
            "trace",
            "--db", str(tmp_path),
            "--file", str(trace_path),
            "--frames", "0",
        ])

    assert exc.value.code == 2


def test_layout_rejects_linked_directory_page(tmp_path):
    catalog = Catalog(tmp_path)
    catalog.create_table("Large", "value:INT")

    heap = HeapFile(tmp_path / "Large.db")

    # Each large record occupies its own data page.
    for _ in range(682):
        heap.insert(b"x" * 4084)

    heap.flush()

    # The first directory holds 681 entries.
    # Page 682 is the second directory page.
    with pytest.raises(SystemExit) as exc:
        main([
            "layout",
            "--db", str(tmp_path),
            "--table", "Large",
            "--page", "682",
        ])

    assert exc.value.code == 2
