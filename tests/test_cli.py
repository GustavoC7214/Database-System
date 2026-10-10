import subprocess
import sys


from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RA_SCRIPT = PROJECT_ROOT / "ra.py"
RELATIONS_FILE = PROJECT_ROOT / "tests" / "relations.ra"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RA_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_execute_query():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name, Age](select[Age>25](Member))",
    )

    assert result.returncode == 0
    assert "Name" in result.stdout
    assert "Age" in result.stdout
    assert "Bob" in result.stdout
    assert "30" in result.stdout
    assert "Charlie" in result.stdout
    assert "35" in result.stdout
    assert result.stderr == ""


def test_tree_mode():
    result = run_cli(
        "--tree",
        "project[Name](select[Age>25](Member))",
    )

    assert result.returncode == 0
    assert "Project(attrs=[Name])" in result.stdout
    assert "Select(cond=Gt(Attr(Age), Num(25)))" in result.stdout
    assert "Relation(Member)" in result.stdout
    assert result.stderr == ""


def test_tree_mode_does_not_require_file():
    result = run_cli(
        "--tree",
        "select[Age>25](Member)",
    )

    assert result.returncode == 0
    assert "Select(cond=Gt(Attr(Age), Num(25)))" in result.stdout
    assert "Relation(Member)" in result.stdout
    assert result.stderr == ""


def test_tree_mode_ignores_file():
    result = run_cli(
        "--tree",
        "--file",
        "this_file_does_not_exist.ra",
        "project[Name](Member)",
    )

    assert result.returncode == 0
    assert "Project(attrs=[Name])" in result.stdout
    assert "Relation(Member)" in result.stdout
    assert result.stderr == ""


def test_empty_result_displays_schema():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name](select[Age>100](Member))",
    )

    assert result.returncode == 0
    assert "Name" in result.stdout
    assert "(no rows)" in result.stdout
    assert result.stderr == ""


def test_name_error():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Unknown](Member)",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Name Error:" in result.stderr
    assert "Unknown" in result.stderr
    assert "Traceback" not in result.stderr


def test_undefined_relation_error():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name](DoesNotExist)",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Name Error:" in result.stderr
    assert "DoesNotExist" in result.stderr
    assert "Traceback" not in result.stderr


def test_lexical_error():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name](Member) @",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Lexical Error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_syntax_error():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name](Member",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Syntax Error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_relation_file():
    result = run_cli(
        "--file",
        "does_not_exist.ra",
        "project[Name](Member)",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "File Error:" in result.stderr
    assert "does_not_exist.ra" in result.stderr
    assert "Traceback" not in result.stderr


def test_query_requires_file():
    result = run_cli(
        "project[Name](Member)",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        "Usage Error: --file is required when executing a query."
        in result.stderr
    )
    assert "Traceback" not in result.stderr


def test_type_error():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "select[Age>'twenty'](Member)",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Type Error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_projection_does_not_print_loaded_relations():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "project[Name](Member)",
    )

    assert result.returncode == 0

    # Query result should be printed.
    assert "Alice" in result.stdout
    assert "Bob" in result.stdout
    assert "Charlie" in result.stdout

    # Loading Chapter should not produce extra output.
    assert "North" not in result.stdout
    assert "South" not in result.stdout

    assert result.stderr == ""


def test_successful_query_has_no_traceback():
    result = run_cli(
        "--file",
        str(RELATIONS_FILE),
        "Member",
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_relation_file_allows_blank_lines_inside_definition(tmp_path):
    relation_file = tmp_path / "relations.ra"

    relation_file.write_text(
        """Member(Id, Name, Age) = {
1, Alice, 25

2, Bob, 30

3, Charlie, 35
}
""",
        encoding="utf-8",
    )

    result = run_cli(
        "--file",
        str(relation_file),
        "Member",
    )

    assert result.returncode == 0
    assert "Alice" in result.stdout
    assert "Bob" in result.stdout
    assert "Charlie" in result.stdout
    assert "Traceback" not in result.stderr