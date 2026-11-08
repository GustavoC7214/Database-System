from collections.abc import Iterator
from typing import Protocol

from src.engine.relation import Relation, Row


class TupleProvider(Protocol):
    def get_relation(self, name: str) -> Relation:
        """Retrieve a relation and its schema."""
        ...

    def iter_rows(self, name: str) -> Iterator[Row]:
        """Iterate over the rows of a relation."""
        ...
