import operator

from src.engine.database import Database
from src.engine.relation import Attribute, Relation, Row
from src.parser.ast import (
    AttributeReference,
    BinaryExpression,
    BinaryOperator,
    BooleanBinaryCondition,
    BooleanOperator,
    Comparison,
    ComparisonOperator,
    Condition,
    Expression,
    Join,
    Not,
    NumberLiteral,
    Operand,
    Project,
    RelationReference,
    Rename,
    Select,
    Sort,
    SortDictionary,
    StringLiteral,
)


class Evaluator:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.join_comparisons = 0
        self.selection_tuples_examined = 0

    def evaluate(self, expression: Expression) -> Relation:
        if isinstance(expression, RelationReference):
            return self.database.get_relation(expression.name)
        
        if isinstance(expression, Select):
            relation = self.evaluate(expression.expression)
            selected_rows = []

            for row in relation.rows:
                self.selection_tuples_examined += 1

                if self.evaluate_condition(expression.condition, relation, row):
                    selected_rows.append(row)

            return Relation(relation.name, relation.attributes, selected_rows)

        if isinstance(expression, Project):
            relation = self.evaluate(expression.expression)
            column_indicies = []

            for attribute in expression.attributes:
                index = self.resolve_attribute(attribute, relation)

                if index in column_indicies:
                    raise ValueError(
                        f"Duplicate projection attribute: {attribute.name}"
                    )

                column_indicies.append(index)

            projected_rows = []

            for row in relation.rows:
                values = [row.values[index] for index in column_indicies]
                projected_rows.append(Row(values))

            projected_attributes = [
                relation.attributes[index] for index in column_indicies
            ]

            return Relation(
                relation.name,
                projected_attributes,
                projected_rows,
            )

        if isinstance(expression, Sort):
            relation = self.evaluate(expression.expression)
            column_index = self.resolve_attribute(expression.attribute, relation)
            sorted_rows = sorted(
                relation.rows,
                key = lambda row: row.values[column_index],
                reverse = expression.direction == SortDictionary.DESC
            )
            return Relation(relation.name, relation.attributes, sorted_rows)

        if isinstance(expression, BinaryExpression):
            if expression.operator == BinaryOperator.TIMES:
                left_relation = self.evaluate(expression.left)
                right_relation = self.evaluate(expression.right)
                combined_attributes = left_relation.attributes + right_relation.attributes
                self.check_attribute_collisions(combined_attributes)
                combined_rows = []

                for left_row in left_relation.rows:
                    for right_row in right_relation.rows:
                        combined_values = left_row.values + right_row.values
                        combined_rows.append(Row(combined_values))

                return Relation(left_relation.name, combined_attributes, combined_rows)
            
            if expression.operator == BinaryOperator.UNION:
                left_relation = self.evaluate(expression.left)
                right_relation = self.evaluate(expression.right)

                self.check_union_compatibility(left_relation, right_relation)

                combined_rows = left_relation.rows + right_relation.rows
                unique_rows = []

                for row in combined_rows:
                    if row not in unique_rows:
                        unique_rows.append(row)

                return Relation(left_relation.name, left_relation.attributes, unique_rows)

            if expression.operator == BinaryOperator.MINUS:
                left_relation = self.evaluate(expression.left)
                right_relation = self.evaluate(expression.right)

                self.check_union_compatibility(left_relation, right_relation)

                difference_rows = []

                for row in left_relation.rows:
                    if row not in right_relation.rows and row not in difference_rows:
                        difference_rows.append(row)

                return Relation(left_relation.name, left_relation.attributes, difference_rows)

            if expression.operator == BinaryOperator.INTERSECT:
                left_relation = self.evaluate(expression.left)
                right_relation = self.evaluate(expression.right)

                self.check_union_compatibility(left_relation, right_relation)

                intersected_rows = []

                for row in left_relation.rows:
                    if row in right_relation.rows and row not in intersected_rows:
                        intersected_rows.append(row)

                return Relation(left_relation.name, left_relation.attributes, intersected_rows)

        if isinstance(expression, Join):
            left_relation = self.evaluate(expression.left)
            right_relation = self.evaluate(expression.right)

            combined_attributes = (
                left_relation.attributes
                + right_relation.attributes
            )

            self.check_attribute_collisions(combined_attributes)

            combined_relation = Relation(
                left_relation.name,
                combined_attributes,
                [],
            )

            joined_rows = []
            
            for left_row in left_relation.rows:
                for right_row in right_relation.rows:
                    self.join_comparisons += 1
                    combined_values = left_row.values + right_row.values
                    combined_row = Row(combined_values)
                    if self.evaluate_condition(expression.condition, combined_relation, combined_row):
                        joined_rows.append(combined_row)

            return Relation(left_relation.name, combined_attributes, joined_rows)

        if isinstance(expression, Rename):
            relation = self.evaluate(expression.expression)

            new_relation_name = expression.new_name
            attribute_renames = expression.attribute_renames

            renamed_attributes = []

            for attribute in relation.attributes:
                renamed_attributes.append(
                    Attribute(
                        new_relation_name,
                        attribute_renames.get(attribute.name, attribute.name),
                    )
                )

            return Relation(
                new_relation_name,
                renamed_attributes,
                relation.rows,
            )
            
        raise NotImplementedError(
            f"Evaluation not implemented for {type(expression).__name__}"
        )

    def check_union_compatibility(
        self,
        left_relation: Relation,
        right_relation: Relation,
    ) -> None:
        if len(left_relation.attributes) != len(right_relation.attributes):
            raise ValueError("Relations are not union-compatible: different attribute counts")

        for left_attribute, right_attribute in zip(
            left_relation.attributes,
            right_relation.attributes,
        ):
            if left_attribute.name != right_attribute.name:
                raise ValueError(
                    "Relations are not union-compatible: "
                    f"attribute names differ ({left_attribute.name} != {right_attribute.name})"
                )

        if left_relation.rows and right_relation.rows:
            for index in range(len(left_relation.attributes)):
                left_value = left_relation.rows[0].values[index]
                right_value = right_relation.rows[0].values[index]

                if type(left_value) is not type(right_value):
                    raise ValueError(
                        "Relations are not union-compatible: incompatible attribute types"
                    )

    def evaluate_condition(self, condition: Condition, relation: Relation, row: Row) -> bool:
        if isinstance(condition, Comparison):
            left = self.evaluate_operand(condition.left, relation, row)
            right = self.evaluate_operand(condition.right, relation, row)

            if type(left) is not type(right):
                raise TypeError("Cannot compare values of different types")

            return self.compare_values(left, condition.operator, right)

        if isinstance(condition, Not):
            return not self.evaluate_condition(condition.condition, relation, row)

        if isinstance(condition, BooleanBinaryCondition):
            if condition.operator == BooleanOperator.AND:
                left = self.evaluate_condition(condition.left, relation, row)
                right = self.evaluate_condition(condition.right, relation, row)
                return left and right
            if condition.operator == BooleanOperator.OR:
                left = self.evaluate_condition(condition.left, relation, row)
                right = self.evaluate_condition(condition.right, relation, row)
                return left or right


        raise NotImplementedError(
            f"Condition evaluation not implemented for {type(condition).__name__}"
        )

    def resolve_attribute(self, reference: AttributeReference, relation: Relation) -> int:
        matches: list[int] = []

        for index, attribute in enumerate(relation.attributes):
            if attribute.name == reference.name and (
                reference.relation is None
                or attribute.relation == reference.relation
            ):
                matches.append(index)

        if len(matches) == 0:
            raise NameError(f"Undefined attribute: {reference.name}")

        if len(matches) > 1:
            raise NameError(f"Ambiguous attribute: {reference.name}")

        return matches[0]

    def evaluate_operand(self, operand: Operand, relation: Relation, row: Row) -> int | str:
        if isinstance(operand, NumberLiteral):
            return operand.value

        if isinstance(operand, StringLiteral):
            return operand.value

        if isinstance(operand, AttributeReference):
            index = self.resolve_attribute(operand, relation)
            return row.values[index]

        raise NotImplementedError(f"Unsupported operand: {type(operand).__name__}")

    def compare_values(
        self,
        left: int | str,
        comparison_operator: ComparisonOperator,
        right: int | str,
        ) -> bool:
            operators = {
                ComparisonOperator.EQUAL: operator.eq,
                ComparisonOperator.NOT_EQUAL: operator.ne,
                ComparisonOperator.LESS_THAN: operator.lt,
                ComparisonOperator.LESS_THAN_OR_EQUAL: operator.le,
                ComparisonOperator.GREATER_THAN: operator.gt,
                ComparisonOperator.GREATER_THAN_OR_EQUAL: operator.ge,
            }

            try:
                compare = operators[comparison_operator]
            except KeyError:
                raise NotImplementedError(
                    f"Unsupported comparison operator: {comparison_operator}"
                ) from None

            if isinstance(left, int) and isinstance(right, int):
                return compare(left, right)

            if isinstance(left, str) and isinstance(right, str):
                return compare(left, right)

            raise TypeError("Cannot compare values of different types")

    def check_attribute_collisions(
        self,
        attributes: list[Attribute],
    ) -> None:
        seen_attributes = set()

        for attribute in attributes:
            qualified_name = (
                attribute.relation,
                attribute.name,
            )

            if qualified_name in seen_attributes:
                raise ValueError(
                    "Attribute collision: "
                    f"{attribute.relation}.{attribute.name}"
                )

            seen_attributes.add(qualified_name)