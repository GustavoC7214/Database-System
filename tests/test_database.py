import pytest

from src.engine.database import Database
from src.engine.relation import Attribute, Relation
from src.parser.ast import RelationDefinition


def test_get_existing_relation():
    database = Database()
    employees = Relation("Employees", [Attribute("Employees", "EID")], [])
    database.add_relation(employees)

    assert database.get_relation("Employees") is employees

def test_get_undefined_relation():
    database = Database()

    with pytest.raises(NameError):
        database.get_relation("Managers")

def test_load_definition():
    database = Database()
    definition = RelationDefinition(
        "Employees",
        ["EID", "Name"],
        [["E1", "John"]],
    )

    database.load_definition(definition)
    relation = database.get_relation("Employees")

    assert len(relation.rows) == 1
    assert relation.rows[0].values == ["E1", "John"]
    assert [attribute.name for attribute in relation.attributes] == ["EID", "Name"]
    assert [attribute.relation for attribute in relation.attributes] == [
        "Employees",
        "Employees",
    ]