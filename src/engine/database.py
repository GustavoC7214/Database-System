from src.engine.relation import Attribute, Relation, Row
from src.parser.ast import RelationDefinition


class Database:
    def __init__(self) -> None:
        self.relations: dict[str, Relation] = {}

    def add_relation(self, relation: Relation) -> None:
        self.relations[relation.name] =  relation

    def get_relation(self, name: str) -> Relation:
        try:
            return self.relations[name]
        except KeyError:
            raise NameError(f"Undefined relation: {name}") from None

    def load_definition(self, definition: RelationDefinition) -> None:
        attributes = [Attribute(definition.name, name) for name in definition.attributes]
        rows = [Row(values) for values in definition.rows]
        relation = Relation(definition.name, attributes, rows)

        self.add_relation(relation)