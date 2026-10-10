from dataclasses import dataclass

Value = int | str


@dataclass
class Attribute:
    relation: str
    name: str

@dataclass
class Row:
    values: list[Value]
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Row):
            return False

        if len(self.values) != len(other.values):
            return False

        for left_value, right_value in zip(self.values, other.values):
            if type(left_value) != type(right_value):
                return False

            if left_value != right_value:
                return False

        return True

@dataclass
class Relation:
    name: str
    attributes: list[Attribute]
    rows: list[Row]
    def __post_init__(self) -> None:
        unique_rows: list[Row] = []

        for row in self.rows:
            if len(row.values) != len(self.attributes):
                raise ValueError(
                    f"Row has {len(row.values)} values but relation has {len(self.attributes)} attributes"
                )
            
            if row not in unique_rows:
                unique_rows.append(row)
        self.rows = unique_rows
