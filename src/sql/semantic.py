"""Semantic analysis for the Module 3 SQL front end.

Resolve names, validate types and aggregates, and determine query output
schemas before constructing logical plans.
"""

from dataclasses import dataclass

from src.sql import ast
from src.sql.catalog import SchemaCatalog, TableSchema


class SQLSemanticError(ValueError):
    """A categorized semantic error with a source location."""

    def __init__(
        self,
        category: str,
        message: str,
        line: int,
        column: int,
    ) -> None:
        self.category = category
        self.line = line
        self.column = column
        super().__init__(
            f"error: {category}: {message} at line {line}, column {column}"
        )


@dataclass(frozen=True, slots=True)
class ResolvedColumn:
    qualified_name: str
    data_type: str

    @property
    def name(self) -> str:
        return self.qualified_name.rsplit(".", 1)[-1]


@dataclass(frozen=True, slots=True)
class ScopeEntry:
    name: str
    columns: tuple[ResolvedColumn, ...]


@dataclass(frozen=True, slots=True)
class ResolvedOutput:
    name: str
    data_type: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzedQuery:
    query: ast.Query
    output: tuple[ResolvedOutput, ...]
    scope: tuple[ScopeEntry, ...] = ()
    selected_columns: tuple[ResolvedColumn, ...] = ()


class NameResolver:
    """Resolve and validate queries against a persistent schema catalog."""

    def __init__(self, catalog: SchemaCatalog) -> None:
        self.catalog = catalog

    @staticmethod
    def _error(
        category: str,
        message: str,
        node: ast.Column | ast.Table | ast.DerivedTable | None = None,
    ) -> SQLSemanticError:
        return SQLSemanticError(
            category,
            message,
            getattr(node, "line", 1),
            getattr(node, "column", 1),
        )

    @staticmethod
    def _type_family(data_type: str) -> str:
        normalized = data_type.upper().strip()
        if normalized == "INT":
            return "INT"
        if normalized.startswith("VARCHAR(") and normalized.endswith(")"):
            return "VARCHAR"
        return normalized

    @classmethod
    def _compatible(cls, left: str, right: str) -> bool:
        return cls._type_family(left) == cls._type_family(right)

    @staticmethod
    def _scope_entry(name: str, table: TableSchema) -> ScopeEntry:
        return ScopeEntry(
            name=name,
            columns=tuple(
                ResolvedColumn(
                    qualified_name=f"{name}.{column.name}",
                    data_type=column.data_type,
                )
                for column in table.columns
            ),
        )

    def _table_entry(self, ref: ast.TableReference) -> ScopeEntry:
        if isinstance(ref, ast.DerivedTable):
            analyzed = self.analyze(ref.query)
            names = [column.name for column in analyzed.output]

            if len(names) != len(set(names)):
                raise self._error(
                    "schema",
                    f"derived table {ref.alias!r} has duplicate output names",
                    ref,
                )

            return ScopeEntry(
                name=ref.alias,
                columns=tuple(
                    ResolvedColumn(
                        qualified_name=f"{ref.alias}.{column.name}",
                        data_type=column.data_type,
                    )
                    for column in analyzed.output
                ),
            )

        try:
            table = self.catalog.get_table(ref.name)
        except ValueError as exc:
            raise self._error(
                "name",
                f"unknown table {ref.name!r}",
                ref,
            ) from exc

        return self._scope_entry(ref.alias or ref.name, table)

    def _add_entry(
        self,
        scope: list[ScopeEntry],
        ref: ast.TableReference,
    ) -> None:
        entry = self._table_entry(ref)

        if any(existing.name == entry.name for existing in scope):
            raise self._error(
                "name",
                f"duplicate table alias {entry.name!r}",
                ref,
            )

        scope.append(entry)

    def resolve_column(
        self,
        column: ast.Column,
        scope: tuple[ScopeEntry, ...] | list[ScopeEntry],
    ) -> ResolvedColumn:
        """Resolve a qualified or unqualified column."""

        if column.qualifier is not None:
            entry = next(
                (item for item in scope if item.name == column.qualifier),
                None,
            )

            if entry is None:
                raise self._error(
                    "name",
                    f"unknown table or alias {column.qualifier!r}",
                    column,
                )

            for candidate in entry.columns:
                if candidate.name == column.name:
                    return candidate

            raise self._error(
                "name",
                f"unknown column {column.name!r} in {entry.name!r}",
                column,
            )

        matches = [
            candidate
            for entry in scope
            for candidate in entry.columns
            if candidate.name == column.name
        ]

        if not matches:
            raise self._error(
                "name",
                f"unknown column {column.name!r}",
                column,
            )

        if len(matches) > 1:
            candidates = ", ".join(match.qualified_name for match in matches)
            raise self._error(
                "ambiguity",
                f"ambiguous column {column.name!r}; candidates: {candidates}",
                column,
            )

        return matches[0]

    def _aggregate_type(
        self,
        expression: ast.Aggregate,
        scope: list[ScopeEntry],
    ) -> tuple[str, ResolvedColumn | None]:
        """Validate an aggregate and determine its result type."""

        function = expression.function.upper()
        argument = (
            self.resolve_column(expression.argument, scope)
            if expression.argument is not None
            else None
        )

        if function == "COUNT":
            return "INT", argument

        if argument is None:
            raise self._error(
                "aggregate",
                f"{function}(*) is not supported",
            )

        if function in ("SUM", "AVG"):
            if self._type_family(argument.data_type) != "INT":
                raise self._error(
                    "aggregate",
                    f"{function} requires INT, got {argument.data_type}",
                    expression.argument,
                )
            return "INT", argument

        if function in ("MIN", "MAX"):
            return argument.data_type, argument

        raise self._error(
            "aggregate",
            f"unknown aggregate function {function}",
            expression.argument,
        )

    def _expression_type(
        self,
        expression: ast.Expression,
        scope: list[ScopeEntry],
        *,
        allow_aggregate: bool,
        aliases: dict[str, ResolvedOutput] | None = None,
        grouped_columns: set[str] | None = None,
    ) -> str:
        """Validate an operand and return its SQL type."""

        if isinstance(expression, ast.Literal):
            if type(expression.value) is int:
                return "INT"
            return "VARCHAR"

        if isinstance(expression, ast.Aggregate):
            if not allow_aggregate:
                raise self._error(
                    "aggregate",
                    "aggregate functions are not allowed here",
                    expression.argument,
                )

            data_type, _ = self._aggregate_type(expression, scope)
            return data_type

        if isinstance(expression, ast.Column):
            if (
                aliases is not None
                and expression.qualifier is None
                and expression.name in aliases
            ):
                return aliases[expression.name].data_type

            resolved = self.resolve_column(expression, scope)

            if (
                grouped_columns is not None
                and resolved.qualified_name not in grouped_columns
            ):
                raise self._error(
                    "aggregate",
                    f"column {resolved.qualified_name!r} "
                    "must appear in GROUP BY or be aggregated",
                    expression,
                )

            return resolved.data_type

        raise self._error("type", "unsupported SQL expression")

    def _validate_condition(
        self,
        condition: ast.Condition,
        scope: list[ScopeEntry],
        *,
        allow_aggregate: bool = False,
        aliases: dict[str, ResolvedOutput] | None = None,
        grouped_columns: set[str] | None = None,
    ) -> None:
        """Validate all operands and comparisons in a condition."""

        if isinstance(condition, ast.Logical):
            self._validate_condition(
                condition.left,
                scope,
                allow_aggregate=allow_aggregate,
                aliases=aliases,
                grouped_columns=grouped_columns,
            )
            self._validate_condition(
                condition.right,
                scope,
                allow_aggregate=allow_aggregate,
                aliases=aliases,
                grouped_columns=grouped_columns,
            )
            return

        if isinstance(condition, ast.Negation):
            self._validate_condition(
                condition.operand,
                scope,
                allow_aggregate=allow_aggregate,
                aliases=aliases,
                grouped_columns=grouped_columns,
            )
            return

        left_type = self._expression_type(
            condition.left,
            scope,
            allow_aggregate=allow_aggregate,
            aliases=aliases,
            grouped_columns=grouped_columns,
        )
        right_type = self._expression_type(
            condition.right,
            scope,
            allow_aggregate=allow_aggregate,
            aliases=aliases,
            grouped_columns=grouped_columns,
        )

        if not self._compatible(left_type, right_type):
            node = (
                condition.left
                if isinstance(condition.left, ast.Column)
                else condition.right
                if isinstance(condition.right, ast.Column)
                else None
            )
            raise self._error(
                "type",
                f"incompatible comparison types: {left_type} and {right_type}",
                node,
            )

    def _analyze_select(self, query: ast.Select) -> AnalyzedQuery:
        scope: list[ScopeEntry] = []
        self._add_entry(scope, query.source)

        for extension in query.extensions:
            self._add_entry(scope, extension.table)

            if extension.condition is not None:
                self._validate_condition(extension.condition, scope)

        if query.where is not None:
            self._validate_condition(query.where, scope)

        grouped_columns = {
            self.resolve_column(column, scope).qualified_name
            for column in query.group_by
        }

        has_aggregates = bool(
            query.columns is not None
            and any(
                isinstance(item.expression, ast.Aggregate) for item in query.columns
            )
        )
        is_aggregating = bool(query.group_by) or has_aggregates

        output: list[ResolvedOutput] = []
        selected: list[ResolvedColumn] = []

        if query.columns is None:
            if is_aggregating:
                raise self._error(
                    "aggregate",
                    "SELECT * is not valid in an aggregating query",
                )

            for entry in scope:
                for column in entry.columns:
                    selected.append(column)
                    output.append(
                        ResolvedOutput(
                            name=column.name,
                            data_type=column.data_type,
                            source=column.qualified_name,
                        )
                    )
        else:
            for item in query.columns:
                expression = item.expression

                if isinstance(expression, ast.Column):
                    resolved = self.resolve_column(expression, scope)

                    if (
                        is_aggregating
                        and resolved.qualified_name not in grouped_columns
                    ):
                        raise self._error(
                            "aggregate",
                            f"column {resolved.qualified_name!r} "
                            "must appear in GROUP BY or be aggregated",
                            expression,
                        )

                    selected.append(resolved)
                    output.append(
                        ResolvedOutput(
                            name=item.alias or resolved.name,
                            data_type=resolved.data_type,
                            source=resolved.qualified_name,
                        )
                    )
                    continue

                if isinstance(expression, ast.Aggregate):
                    data_type, argument = self._aggregate_type(
                        expression,
                        scope,
                    )

                    generated_name = (
                        expression.function.lower()
                        + "_"
                        + (
                            argument.qualified_name.replace(".", "_")
                            if argument is not None
                            else "star"
                        )
                    )

                    output.append(
                        ResolvedOutput(
                            name=item.alias or generated_name,
                            data_type=data_type,
                        )
                    )
                    continue

                raise self._error(
                    "type",
                    "unsupported SELECT expression",
                )

        aliases = {
            item.alias: result
            for item, result in zip(query.columns or (), output)
            if item.alias is not None
        }

        if query.having is not None:
            if not is_aggregating:
                raise self._error(
                    "aggregate",
                    "HAVING requires GROUP BY or an aggregate query",
                )

            self._validate_condition(
                query.having,
                scope,
                allow_aggregate=True,
                aliases=aliases,
                grouped_columns=grouped_columns,
            )

        for sort_item in query.order_by:
            column = sort_item.column

            if column.qualifier is None and column.name in aliases:
                continue

            self._expression_type(
                column,
                scope,
                allow_aggregate=False,
                grouped_columns=(grouped_columns if is_aggregating else None),
            )

        return AnalyzedQuery(
            query=query,
            output=tuple(output),
            scope=tuple(scope),
            selected_columns=tuple(selected),
        )

    def analyze(self, query: ast.Query) -> AnalyzedQuery:
        """Validate a SELECT or a set-operation query tree."""

        if isinstance(query, ast.Select):
            return self._analyze_select(query)

        left = self.analyze(query.left)
        right = self.analyze(query.right)

        if len(left.output) != len(right.output):
            raise self._error(
                "schema",
                f"{query.operator} requires the same number of columns: "
                f"left has {len(left.output)}, "
                f"right has {len(right.output)}",
            )

        for position, (left_col, right_col) in enumerate(
            zip(left.output, right.output),
            start=1,
        ):
            if not self._compatible(
                left_col.data_type,
                right_col.data_type,
            ):
                raise self._error(
                    "type",
                    f"{query.operator} column {position} has "
                    f"incompatible types: "
                    f"{left_col.data_type} and {right_col.data_type}",
                )

        return AnalyzedQuery(
            query=query,
            output=left.output,
        )
