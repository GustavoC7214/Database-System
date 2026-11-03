"""Canonical logical-plan compiler for the Module 3 SQL subset.

Plans are JSON-serializable dictionaries. This module performs no query
execution, physical-operator selection, or predicate pushdown.
"""

import json
from typing import Any, TypeAlias

from src.sql import ast
from src.sql.catalog import SchemaCatalog
from src.sql.parser import parse_sql
from src.sql.semantic import AnalyzedQuery, NameResolver, ScopeEntry

Plan: TypeAlias = dict[str, Any]


class SQLCompiler:
    """Compile semantically valid SQL queries into logical operator trees."""

    def __init__(self, catalog: SchemaCatalog) -> None:
        self.resolver = NameResolver(catalog)

    def compile(self, query: ast.Query) -> Plan:
        """Validate a query and compile it into a logical plan."""
        analyzed = self.resolver.analyze(query)
        return self._compile_query(query, analyzed)

    def compile_sql(self, source: str) -> list[Plan]:
        """Parse and compile query statements from SQL source."""
        plans: list[Plan] = []

        for statement in parse_sql(source):
            if not isinstance(statement, (ast.Select, ast.SetOperation)):
                raise TypeError(
                    "Logical-plan compilation currently supports SELECT "
                    "queries only; CREATE TABLE and INSERT require "
                    "statement-specific handling."
                )
            plans.append(self.compile(statement))

        return plans

    def _compile_query(
        self,
        query: ast.Query,
        analyzed: AnalyzedQuery,
    ) -> Plan:
        if isinstance(query, ast.Select):
            return self._compile_select(query, analyzed)

        left = self.resolver.analyze(query.left)
        right = self.resolver.analyze(query.right)

        operator = query.operator.upper().replace(" ", "_")

        if operator not in {
            "UNION",
            "UNION_ALL",
            "INTERSECT",
            "EXCEPT",
        }:
            raise ValueError(f"Unsupported set operator: {query.operator}")

        return {
            "op": operator.lower(),
            "left": self._compile_query(query.left, left),
            "right": self._compile_query(query.right, right),
        }

    def _table(self, ref: ast.TableReference) -> Plan:
        if isinstance(ref, ast.DerivedTable):
            analyzed = self.resolver.analyze(ref.query)
            return {
                "op": "rename",
                "to": ref.alias,
                "child": self._compile_query(ref.query, analyzed),
            }

        plan: Plan = {
            "op": "scan",
            "table": ref.name,
        }

        if ref.alias is not None:
            plan = {
                "op": "rename",
                "to": ref.alias,
                "child": plan,
            }

        return plan

    def _column(
        self,
        column: ast.Column,
        scope: tuple[ScopeEntry, ...],
    ) -> str:
        return self.resolver.resolve_column(
            column,
            scope,
        ).qualified_name

    def _expression(
        self,
        expression: ast.Expression,
        scope: tuple[ScopeEntry, ...],
        aliases: dict[str, str] | None = None,
    ) -> str:
        if isinstance(expression, ast.Literal):
            if isinstance(expression.value, str):
                escaped = expression.value.replace("'", "''")
                return f"'{escaped}'"
            return str(expression.value)

        if isinstance(expression, ast.Column):
            if (
                aliases is not None
                and expression.qualifier is None
                and expression.name in aliases
            ):
                return aliases[expression.name]

            return self._column(expression, scope)

        function = expression.function.upper()
        argument = (
            self._column(expression.argument, scope)
            if expression.argument is not None
            else "*"
        )
        return f"{function}({argument})"

    def _condition(
        self,
        condition: ast.Condition,
        scope: tuple[ScopeEntry, ...],
        aliases: dict[str, str] | None = None,
    ) -> str:
        if isinstance(condition, ast.Comparison):
            left = self._expression(condition.left, scope, aliases)
            right = self._expression(condition.right, scope, aliases)
            return f"{left} {condition.operator} {right}"

        if isinstance(condition, ast.Negation):
            operand = self._condition(
                condition.operand,
                scope,
                aliases,
            )
            return f"NOT ({operand})"

        left = self._condition(condition.left, scope, aliases)
        right = self._condition(condition.right, scope, aliases)

        return f"({left} {condition.operator.upper()} {right})"

    def _from(
        self,
        query: ast.Select,
        scope: tuple[ScopeEntry, ...],
    ) -> Plan:
        plan = self._table(query.source)

        for index, extension in enumerate(query.extensions, start=2):
            right = self._table(extension.table)
            join_scope = scope[:index]

            if extension.kind.upper() == "CROSS":
                plan = {
                    "op": "cross",
                    "left": plan,
                    "right": right,
                }
            elif extension.kind.upper() == "JOIN":
                if extension.condition is None:
                    raise ValueError("JOIN requires an ON condition")

                plan = {
                    "op": "join",
                    "condition": self._condition(
                        extension.condition,
                        join_scope,
                    ),
                    "left": plan,
                    "right": right,
                }
            else:
                raise ValueError(f"Unsupported FROM extension: {extension.kind}")

        return plan

    def _aggregates(
        self,
        query: ast.Select,
        scope: tuple[ScopeEntry, ...],
    ) -> tuple[list[list[str]], dict[str, str]]:
        """Collect unique aggregates in SELECT and HAVING.

        Aggregate entries use [function, argument, output_name].
        """
        aggregates: list[list[str]] = []
        names: dict[str, str] = {}
        used_names: set[str] = set()

        def register(
            expression: ast.Aggregate,
            preferred_name: str | None = None,
        ) -> None:
            signature = self._expression(expression, scope)

            if signature in names:
                return

            argument = (
                self._column(expression.argument, scope)
                if expression.argument is not None
                else "*"
            )

            generated = (
                expression.function.lower()
                + "_"
                + argument.replace(".", "_").replace("*", "star")
            )
            name = preferred_name or generated

            if name in used_names:
                suffix = 2
                while f"{name}_{suffix}" in used_names:
                    suffix += 1
                name = f"{name}_{suffix}"

            used_names.add(name)
            names[signature] = name
            aggregates.append([expression.function.lower(), argument, name])

        for item in query.columns or ():
            if isinstance(item.expression, ast.Aggregate):
                register(item.expression, item.alias)

        def visit(condition: ast.Condition) -> None:
            if isinstance(condition, ast.Comparison):
                for operand in (condition.left, condition.right):
                    if isinstance(operand, ast.Aggregate):
                        register(operand)
            elif isinstance(condition, ast.Negation):
                visit(condition.operand)
            else:
                visit(condition.left)
                visit(condition.right)

        if query.having is not None:
            visit(query.having)

        return aggregates, names

    def _having_condition(
        self,
        condition: ast.Condition,
        scope: tuple[ScopeEntry, ...],
        aliases: dict[str, str],
        aggregate_names: dict[str, str],
    ) -> str:
        """Render HAVING using the outputs of the group_by operator."""

        def operand(expression: ast.Expression) -> str:
            if isinstance(expression, ast.Aggregate):
                signature = self._expression(expression, scope)
                return aggregate_names[signature]

            return self._expression(expression, scope, aliases)

        def visit(node: ast.Condition) -> str:
            if isinstance(node, ast.Comparison):
                return f"{operand(node.left)} {node.operator} {operand(node.right)}"
            if isinstance(node, ast.Negation):
                return f"NOT ({visit(node.operand)})"
            return f"({visit(node.left)} {node.operator.upper()} {visit(node.right)})"

        return visit(condition)

    def _compile_select(
        self,
        query: ast.Select,
        analyzed: AnalyzedQuery,
    ) -> Plan:
        scope = analyzed.scope

        # FROM
        plan = self._from(query, scope)

        # WHERE
        if query.where is not None:
            plan = {
                "op": "select",
                "condition": self._condition(query.where, scope),
                "child": plan,
            }

        aggregates, aggregate_names = self._aggregates(query, scope)
        grouping = bool(query.group_by) or bool(aggregates)

        # GROUP BY
        if grouping:
            plan = {
                "op": "group_by",
                "keys": [self._column(column, scope) for column in query.group_by],
                "aggregates": aggregates,
                "child": plan,
            }

        # Resolve SELECT aliases to their input expressions.
        aliases: dict[str, str] = {}

        for item in query.columns or ():
            if item.alias is None:
                continue

            if isinstance(item.expression, ast.Aggregate):
                signature = self._expression(item.expression, scope)
                aliases[item.alias] = aggregate_names[signature]
            else:
                aliases[item.alias] = self._column(
                    item.expression,
                    scope,
                )

        # HAVING references the outputs of GROUP BY.
        if query.having is not None:
            plan = {
                "op": "select",
                "condition": self._having_condition(
                    query.having,
                    scope,
                    aliases,
                    aggregate_names,
                ),
                "child": plan,
            }

        # Determine the source expressions and output names.
        if query.columns is None:
            columns = [column.qualified_name for column in analyzed.selected_columns]
            output_names = list(columns)
        else:
            columns = []
            output_names = []

            for item in query.columns:
                if isinstance(item.expression, ast.Aggregate):
                    signature = self._expression(
                        item.expression,
                        scope,
                    )
                    source_name = aggregate_names[signature]
                else:
                    source_name = self._column(
                        item.expression,
                        scope,
                    )

                columns.append(source_name)

                if item.alias is not None:
                    output_names.append(item.alias)
                elif isinstance(item.expression, ast.Column):
                    output_names.append(source_name)
                else:
                    output_names.append(source_name)

        # Preserve each output position, including repeated
        # expressions with different aliases.
        projection_aliases = {
            output: source
            for output, source in zip(
                output_names,
                columns,
                strict=True,
            )
            if output != source
        }

        # Preserve output aliases separately from input expressions.
        projection_aliases = {
            alias: source for alias, source in aliases.items() if alias != source
        }

        projected_names = {
            next(
                (alias for alias, source in aliases.items() if source == column),
                column,
            )
            for column in columns
        }

        # Resolve sorting references and determine whether they
        # remain available after projection.
        sorts: list[list[str]] = []
        sort_requires_input = False

        for item in query.order_by:
            column = item.column

            if column.qualifier is None and column.name in aliases:
                sort_name = column.name
                source_name = aliases[column.name]
            else:
                source_name = self._column(column, scope)
                sort_name = source_name

            sorts.append([sort_name, item.direction.lower()])

            if sort_name not in projected_names:
                sort_requires_input = True

        # Sorting on a non-projected column must happen while
        # that column is still available.
        #
        # ORDER BY output aliases is handled after projection.
        if sort_requires_input:
            if query.distinct:
                raise ValueError(
                    "ORDER BY non-selected columns with DISTINCT "
                    "is not supported by this logical-plan format"
                )

            input_sorts = [
                [aliases.get(name, name), direction] for name, direction in sorts
            ]

            plan = {
                "op": "sort",
                "keys": input_sorts,
                "child": plan,
            }

        # SELECT projection
        project: Plan = {
            "op": "project",
            "columns": columns,
            "child": plan,
        }

        if projection_aliases:
            project["aliases"] = projection_aliases
            project["outputs"] = output_names

        if projection_aliases:
            project["aliases"] = projection_aliases

        plan = project

        # DISTINCT applies to the projected output.
        if query.distinct:
            plan = {
                "op": "distinct",
                "child": plan,
            }

        # Normal sorting happens after projection and DISTINCT.
        if sorts and not sort_requires_input:
            plan = {
                "op": "sort",
                "keys": sorts,
                "child": plan,
            }

        # LIMIT is always the outermost SELECT operator.
        if query.limit is not None:
            plan = {
                "op": "limit",
                "count": query.limit,
                "child": plan,
            }

        return plan


def compile_sql(source: str, catalog: SchemaCatalog) -> list[Plan]:
    """Convenience function for compiling SQL source."""
    return SQLCompiler(catalog).compile_sql(source)


def plan_json(plan: Plan, *, indent: int = 2) -> str:
    """Serialize a logical plan as deterministic JSON."""
    return json.dumps(plan, indent=indent, ensure_ascii=False)
