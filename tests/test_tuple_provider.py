from collections.abc import Iterator

from src.engine.database import Database
from src.engine.evaluator import Evaluator
from src.engine.relation import Attribute, Relation, Row
from src.parser.ast import RelationReference


def test_database_iter_rows():
    database = Database()

    relation = Relation(
        "R",
        [Attribute("R", "a")],
        [Row([1]), Row([2]), Row([3])],
    )

    database.add_relation(relation)

    rows = list(database.iter_rows("R"))

    assert rows == [Row([1]), Row([2]), Row([3])]


def test_database_iter_rows_empty():
    database = Database()

    database.add_relation(
        Relation("R", [Attribute("R", "a")], [])
    )

    assert list(database.iter_rows("R")) == []

class MockTupleProvider:
    def get_relation(self, name: str) -> Relation:
        if name != "Employees":
            raise NameError(f"Undefined relation: {name}")

        return Relation(
            "Employees",
            [
                Attribute("Employees", "EID"),
                Attribute("Employees", "Name"),
            ],
            [],
        )

    def iter_rows(self, name: str) -> Iterator[Row]:
        if name != "Employees":
            raise NameError(f"Undefined relation: {name}")

        yield Row([1, "Alice"])
        yield Row([2, "Bob"])
        yield Row([3, "Charlie"])


def test_evaluator_with_custom_tuple_provider():
    provider = MockTupleProvider()
    evaluator = Evaluator(provider)

    result = evaluator.evaluate(RelationReference("Employees"))

    assert result.name == "Employees"
    assert result.attributes == [
        Attribute("Employees", "EID"),
        Attribute("Employees", "Name"),
    ]
    assert result.rows == [
        Row([1, "Alice"]),
        Row([2, "Bob"]),
        Row([3, "Charlie"]),
    ]