"""Handwritten recursive-descent SQL parser for COMP 3005 Module 3."""

from src.sql import ast
from src.sql.tokenizer import tokenize
from src.sql.tokens import Token, TokenType


class SQLSyntaxError(ValueError):
    """A syntax error with an exact source location."""

    def __init__(self, message: str, token: Token) -> None:
        self.line = token.line
        self.column = token.column
        super().__init__(
            f"error: syntax: {message} at line {token.line}, column {token.column}"
        )


class SQLParser:
    """Parse the supported SQL subset into immutable AST nodes."""

    def __init__(self, source: str) -> None:
        self.tokens = tokenize(source)
        self.position = 0

    def _current(self) -> Token:
        return self.tokens[self.position]

    def _advance(self) -> Token:
        token = self._current()
        if token.type != TokenType.EOF:
            self.position += 1
        return token

    def _match_value(self, *values: str) -> bool:
        if self._current().value in values:
            self._advance()
            return True
        return False

    def _expect_value(self, value: str) -> Token:
        token = self._current()
        if not self._match_value(value):
            raise SQLSyntaxError(f"expected {value!r}", token)
        return token

    def _expect_identifier(self) -> str:
        token = self._current()
        if token.type != TokenType.IDENTIFIER:
            raise SQLSyntaxError("expected identifier", token)
        self._advance()
        return token.value

    def _expect_integer(self) -> int:
        token = self._current()
        if token.type != TokenType.INTEGER:
            raise SQLSyntaxError("expected integer", token)
        self._advance()
        return int(token.value)

    def _positive_integer(self) -> int:
        token = self._current()
        value = self._expect_integer()
        if value <= 0:
            raise SQLSyntaxError("expected positive integer", token)
        return value

    def _nonnegative_integer(self) -> int:
        token = self._current()
        value = self._expect_integer()
        if value < 0:
            raise SQLSyntaxError("expected nonnegative integer", token)
        return value

    def parse(self) -> tuple[ast.Statement, ...]:
        """Parse one or more semicolon-separated statements."""
        statements: list[ast.Statement] = []

        while self._current().type != TokenType.EOF:
            if self._match_value(";"):
                continue

            statements.append(self._statement())

            if self._current().type == TokenType.EOF:
                break

            self._expect_value(";")

        return tuple(statements)

    def _statement(self) -> ast.Statement:
        value = self._current().value

        if value == "CREATE":
            return self._create_table()
        if value == "INSERT":
            return self._insert()
        if value in ("SELECT", "("):
            return self._query()

        raise SQLSyntaxError("expected SQL statement", self._current())

    def _create_table(self) -> ast.CreateTable:
        self._expect_value("CREATE")
        self._expect_value("TABLE")
        name = self._expect_identifier()
        self._expect_value("(")

        columns = [self._column_definition()]
        while self._match_value(","):
            columns.append(self._column_definition())

        self._expect_value(")")
        return ast.CreateTable(name, tuple(columns))

    def _column_definition(self) -> ast.ColumnDefinition:
        name = self._expect_identifier()

        if self._match_value("INT"):
            return ast.ColumnDefinition(name, "INT")

        self._expect_value("VARCHAR")
        self._expect_value("(")
        length = self._positive_integer()
        self._expect_value(")")
        return ast.ColumnDefinition(name, "VARCHAR", length)

    def _insert(self) -> ast.Insert:
        self._expect_value("INSERT")
        self._expect_value("INTO")
        table = self._expect_identifier()
        self._expect_value("VALUES")
        self._expect_value("(")

        values = [self._literal()]
        while self._match_value(","):
            values.append(self._literal())

        self._expect_value(")")
        return ast.Insert(table, tuple(values))

    def _literal(self) -> ast.Literal:
        token = self._current()

        if token.type == TokenType.INTEGER:
            self._advance()
            return ast.Literal(int(token.value))

        if token.type == TokenType.STRING:
            self._advance()
            return ast.Literal(token.value)

        raise SQLSyntaxError("expected literal", token)

    def _query(self) -> ast.Query:
        left = self._query_term()

        while self._current().value in (
            "UNION",
            "INTERSECT",
            "EXCEPT",
        ):
            operator = self._advance().value

            if operator == "UNION" and self._match_value("ALL"):
                operator = "UNION ALL"

            right = self._query_term()
            left = ast.SetOperation(operator, left, right)

        return left

    def _query_term(self) -> ast.Query:
        if self._match_value("("):
            query = self._query()
            self._expect_value(")")
            return query

        return self._select()

    def _select(self) -> ast.Select:
        self._expect_value("SELECT")
        distinct = self._match_value("DISTINCT")

        if self._match_value("*"):
            columns = None
        else:
            items = [self._select_item()]
            while self._match_value(","):
                items.append(self._select_item())
            columns = tuple(items)

        self._expect_value("FROM")
        source = self._table_reference()

        extensions: list[ast.FromExtension] = []

        while True:
            if self._match_value(","):
                extensions.append(ast.FromExtension("CROSS", self._table_reference()))
            elif self._match_value("JOIN"):
                table = self._table_reference()
                self._expect_value("ON")
                condition = self._condition()
                extensions.append(ast.FromExtension("JOIN", table, condition))
            else:
                break

        where = None
        if self._match_value("WHERE"):
            where = self._condition()

        group_by: tuple[ast.Column, ...] = ()
        having = None

        if self._match_value("GROUP"):
            self._expect_value("BY")
            group_by = self._column_list()

            if self._match_value("HAVING"):
                having = self._condition()

        order_by: tuple[ast.SortItem, ...] = ()
        if self._match_value("ORDER"):
            self._expect_value("BY")
            items = [self._sort_item()]
            while self._match_value(","):
                items.append(self._sort_item())
            order_by = tuple(items)

        limit = None
        if self._match_value("LIMIT"):
            limit = self._nonnegative_integer()

        return ast.Select(
            distinct=distinct,
            columns=columns,
            source=source,
            extensions=tuple(extensions),
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
        )

    def _table_reference(self) -> ast.TableReference:
        token = self._current()

        if self._match_value("("):
            query = self._query()
            self._expect_value(")")
            self._expect_value("AS")
            alias = self._expect_identifier()

            return ast.DerivedTable(
                query=query,
                alias=alias,
                line=token.line,
                column=token.column,
            )

        name = self._expect_identifier()
        alias = None

        if self._match_value("AS") or self._current().type == TokenType.IDENTIFIER:
            alias = self._expect_identifier()

        return ast.Table(
            name=name,
            alias=alias,
            line=token.line,
            column=token.column,
        )

    def _select_item(self) -> ast.SelectItem:
        expression = self._expression()
        if not isinstance(expression, (ast.Column, ast.Aggregate)):
            raise SQLSyntaxError("expected column or aggregate", self._current())

        alias = None
        if self._match_value("AS"):
            alias = self._expect_identifier()

        return ast.SelectItem(expression, alias)

    def _expression(self) -> ast.Expression:
        if self._current().value in (
            "COUNT",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
        ):
            return self._aggregate()

        token = self._current()
        if token.type in (TokenType.INTEGER, TokenType.STRING):
            return self._literal()

        return self._column()

    def _aggregate(self) -> ast.Aggregate:
        function = self._advance().value
        self._expect_value("(")

        if self._match_value("*"):
            if function != "COUNT":
                raise SQLSyntaxError("only COUNT supports *", self._current())
            argument = None
        else:
            argument = self._column()

        self._expect_value(")")
        return ast.Aggregate(function, argument)

    def _column(self) -> ast.Column:
        token = self._current()
        first = self._expect_identifier()

        if self._match_value("."):
            return ast.Column(
                name=self._expect_identifier(),
                qualifier=first,
                line=token.line,
                column=token.column,
            )

        return ast.Column(
            name=first,
            line=token.line,
            column=token.column,
        )

    def _column_list(self) -> tuple[ast.Column, ...]:
        columns = [self._column()]
        while self._match_value(","):
            columns.append(self._column())
        return tuple(columns)

    def _sort_item(self) -> ast.SortItem:
        column = self._column()
        direction = "ASC"

        if self._match_value("DESC"):
            direction = "DESC"
        else:
            self._match_value("ASC")

        return ast.SortItem(column, direction)

    def _condition(self) -> ast.Condition:
        return self._or_condition()

    def _or_condition(self) -> ast.Condition:
        left = self._and_condition()

        while self._match_value("OR"):
            right = self._and_condition()
            left = ast.Logical("OR", left, right)

        return left

    def _and_condition(self) -> ast.Condition:
        left = self._not_condition()

        while self._match_value("AND"):
            right = self._not_condition()
            left = ast.Logical("AND", left, right)

        return left

    def _not_condition(self) -> ast.Condition:
        if self._match_value("NOT"):
            return ast.Negation(self._not_condition())

        if self._match_value("("):
            condition = self._condition()
            self._expect_value(")")
            return condition

        return self._comparison()

    def _comparison(self) -> ast.Comparison:
        left = self._expression()
        token = self._current()

        if token.type != TokenType.OPERATOR:
            raise SQLSyntaxError("expected comparison operator", token)

        operator = self._advance().value
        right = self._expression()

        return ast.Comparison(left, operator, right)


def parse_sql(source: str) -> tuple[ast.Statement, ...]:
    """Parse SQL text into a tuple of statements."""
    return SQLParser(source).parse()
