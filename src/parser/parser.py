from src.lexer.token import Token, TokenType
from src.parser.ast import (
    ASTNode,
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
    RelationDefinition,
    RelationReference,
    RelationValue,
    Rename,
    Select,
    Sort,
    SortDictionary,
    StringLiteral,
)


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.current = 0

    def parse(self) -> ASTNode:
        if (
            self.check(TokenType.IDENTIFIER)
            and self.peek_next().type == TokenType.LPAREN
        ):
            result = self.parse_relation_definition()
        else:
            result = self.parse_expression()

        if not self.check(TokenType.EOF):
            token = self.peek()
            raise ParseError(
                f"Unexpected token {token.type} at"
                f"line {token.position.line}, column {token.position.column}"
            )

        return result

    def parse_expression(self) -> Expression:
        return self.parse_set_expression()

    def parse_set_expression(self) -> Expression:
        left = self.parse_product_expression()

        while(
            self.check_keyword("union")
            or self.check_keyword("intersect")
            or self.check_keyword("minus")
        ):
            operator_token = self.advance()
            right = self.parse_product_expression()
            left = BinaryExpression(
                left = left,
                operator = BinaryOperator(operator_token.value),
                right = right
            )
        
        return left

    def parse_product_expression(self) -> Expression:
        left = self.parse_primary_expression()

        while (
            self.check_keyword("times")
            or self.check_keyword("join")
        ):
            operator_token = self.advance()
            if operator_token.value == "join":
                self.expect(TokenType.LBRACKET)
                condition = self.parse_condition()
                self.expect(TokenType.RBRACKET)

                right = self.parse_primary_expression()

                left = Join(
                    left = left,
                    condition = condition,
                    right = right
                )
            else:
                right = self.parse_primary_expression()

                left = BinaryExpression(
                    left = left,
                    operator = BinaryOperator(operator_token.value),
                    right = right
                )

        return left

    def parse_primary_expression(self) -> Expression:
        if (
            self.check_keyword("select")
            and self.peek_next().type == TokenType.LBRACKET
        ):
            return self.parse_select_expression()
        elif (self.check_keyword("project")
              and self.peek_next().type == TokenType.LBRACKET
        ):
            return self.parse_project_expression()
        elif (self.check_keyword("rename")
              and self.peek_next().type == TokenType.LBRACKET
              ):
            return self.parse_rename_expression()
        elif (self.check_keyword("sort")
              and self.peek_next().type == TokenType.LBRACKET
        ):
            return self.parse_sort_expression()
        

        if self.match(TokenType.LPAREN):
            expression = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expression
        if self.check(TokenType.IDENTIFIER):
            token = self.expect(TokenType.IDENTIFIER)
            return RelationReference(name=token.value)

        token = self.peek()
        raise ParseError(
            f"Expected expression, but found {token.type},"
            f'at line {token.position.line}, column {token.position.column}'
        )

    def parse_sort_expression(self) -> Expression:
        self.match_keyword("sort")
        self.expect(TokenType.LBRACKET)

        attribute = self.parse_attribute()
        direction_token = self.expect(TokenType.IDENTIFIER)

        if direction_token.value not in ("asc", "desc"):
            raise ParseError(
                f"Expected 'asc' or 'desc', but found '{direction_token.value}' "
                f"at line {direction_token.position.line}, "
                f"column {direction_token.position.column}"
            )

        self.expect(TokenType.RBRACKET)
        self.expect(TokenType.LPAREN)
        expression = self.parse_expression()
        self.expect(TokenType.RPAREN)

        return Sort(
            attribute=attribute,
            direction=SortDictionary(direction_token.value),
            expression=expression,
        )
    
    def parse_select_expression(self) -> Expression:
        self.match_keyword("select")
        self.expect(TokenType.LBRACKET)
        condition = self.parse_condition()
        self.expect(TokenType.RBRACKET)
        self.expect(TokenType.LPAREN)
        expression = self.parse_expression()
        self.expect(TokenType.RPAREN)

        return Select(
            condition = condition,
            expression = expression
        )

    def parse_project_expression(self) -> Expression:
        self.match_keyword("project")
        self.expect(TokenType.LBRACKET)
        attributes = self.parse_attribute_list()
        self.expect(TokenType.RBRACKET)
        self.expect(TokenType.LPAREN)
        expression = self.parse_expression()
        self.expect(TokenType.RPAREN)

        return Project(
            attributes = attributes,
            expression = expression
        )

    def parse_rename_expression(self) -> Expression:
        self.match_keyword("rename")
        self.expect(TokenType.LBRACKET)
        new_name = self.expect(TokenType.IDENTIFIER)
        self.expect(TokenType.RBRACKET)
        self.expect(TokenType.LPAREN)
        expression = self.parse_expression()
        self.expect(TokenType.RPAREN)

        return Rename(
            new_name = new_name.value,
            expression = expression
        )

    def parse_attribute(self) -> AttributeReference:
        first = self.expect(TokenType.IDENTIFIER)

        if self.match(TokenType.DOT):
            second = self.expect(TokenType.IDENTIFIER)

            return AttributeReference(
                name = second.value,
                relation = first.value
            )

        return AttributeReference(
            name = first.value
        )

    def parse_attribute_list(self) -> list[AttributeReference]:
        attributes = [self.parse_attribute()]

        while self.match(TokenType.COMMA):
            attributes.append(self.parse_attribute())

        return attributes

    def parse_condition(self) -> Condition:
        return self.parse_or_condition()

    def parse_or_condition(self) -> Condition:
        left = self.parse_and_condition()

        while self.check_keyword("or"):
            self.advance()
            right = self.parse_and_condition()

            left = BooleanBinaryCondition (
                left = left,
                operator = BooleanOperator.OR,
                right = right
            )
        return left

    def parse_and_condition(self) -> Condition:
        left = self.parse_not_condition()

        while self.check_keyword("and"):
            self.advance()
            right = self.parse_not_condition()

            left = BooleanBinaryCondition(
                left = left,
                operator = BooleanOperator.AND,
                right = right
            )

        return left

    def parse_not_condition(self) -> Condition:
        if (
            self.check_keyword("not")
            and self.peek_next().type not in (
            TokenType.COMPARISON_OPERATOR,
            TokenType.DOT
            )
        ):
            self.advance()
            condition = self.parse_not_condition()
            return Not(condition = condition)

        return self.parse_condition_primary()

    def parse_condition_primary(self) -> Condition:
        if self.match(TokenType.LPAREN):
            condition = self.parse_condition()
            self.expect(TokenType.RPAREN)
            return condition

        return self.parse_comparison()

    def parse_comparison(self) -> Condition:
        left = self.parse_operand()
        operator_token = self.expect(TokenType.COMPARISON_OPERATOR)
        right = self.parse_operand()

        return Comparison(
            left = left,
            operator = ComparisonOperator(operator_token.value),
            right = right
        )

    def parse_operand(self) -> Operand:
        if self.check(TokenType.NUMBER):
            token = self.advance()
            return NumberLiteral(value = int(token.value))

        if self.check(TokenType.STRING):
            token = self.advance()
            return StringLiteral(value = token.value)

        if self.check(TokenType.IDENTIFIER):
            return self.parse_attribute()

        token = self.peek()
        raise ParseError(
            f"Expected operand, but found {token.type},"
            f"at line {token.position.line}, column {token.position.column}"
        )

    def parse_relation_value(self) -> RelationValue:
        if self.check(TokenType.NUMBER):
            token = self.advance()
            return int(token.value)

        if self.check(TokenType.STRING) or self.check(TokenType.BARE_STRING):
            token = self.advance()
            return token.value

        token = self.peek()
        raise ParseError(
            f"Expected relation value, but found {token.type} "
            f"at line {token.position.line}, column {token.position.column}"
        )

    def parse_tuple(self) -> list[RelationValue]:
        values = [self.parse_relation_value()]

        while self.match(TokenType.COMMA):
            values.append(self.parse_relation_value())

        return values

    def parse_relation_definition(self) -> RelationDefinition:
        name = self.expect(TokenType.IDENTIFIER)
        self.expect(TokenType.LPAREN)
        attributes = self.parse_attribute_name_list()
        self.expect(TokenType.RPAREN)

        operator = self.expect(TokenType.COMPARISON_OPERATOR)

        if operator.value != "=":
            raise ParseError(
                f"Expected '=', but found '{operator.value}' at "
                f"line {operator.position.line}, column {operator.position.column}"
            )

        self.expect(TokenType.LBRACE)
        self.expect(TokenType.NEWLINE)

        rows = []
        while not (self.check(TokenType.RBRACE)):
            row = self.parse_tuple()
            self.expect(TokenType.NEWLINE)
            rows.append(row)

        self.expect(TokenType.RBRACE)
        return RelationDefinition(
            name = name.value,
            attributes= attributes,
            rows= rows
        )

    def parse_attribute_name_list(self) -> list[str]:
        attributes = [self.expect(TokenType.IDENTIFIER).value]

        while self.match(TokenType.COMMA):
            attributes.append(
                self.expect(TokenType.IDENTIFIER).value
        )

        return attributes


    # Helper Functions

    def peek(self) -> Token:
        return self.tokens[self.current]

    def peek_next(self) -> Token:
        if self.current + 1 >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.current + 1]

    def advance(self) -> Token:
        token = self.tokens[self.current]
        self.current += 1
        return token

    def check(self, token_type: TokenType) -> bool:
        return self.peek().type == token_type

    def match(self, token_type: TokenType) -> bool:
        if self.check(token_type):
            self.advance()
            return True
        return False

    def expect(self, token_type: TokenType) -> Token:
        if self.check(token_type):
            return self.advance()

        token = self.peek()

        expected = self.token_display_name(token_type)
        found = self.token_display_name(token.type)

        raise ParseError(
            f"Expected {expected} but found {found} "
            f"at line {token.position.line}, column {token.position.column}"
        )

    def check_keyword(self, keyword: str) -> bool:
        return self.peek().type == TokenType.IDENTIFIER and self.peek().value == keyword

    def match_keyword(self, keyword: str) -> bool:
        if self.check_keyword(keyword):
            self.advance()
            return True
        return False

    def token_display_name(self, token_type: TokenType) -> str:
        names = {
            TokenType.LPAREN: "'('",
            TokenType.RPAREN: "')'",
            TokenType.LBRACKET: "'['",
            TokenType.RBRACKET: "']'",
            TokenType.LBRACE: "'{'",
            TokenType.RBRACE: "'}'",
            TokenType.COMMA: "','",
            TokenType.DOT: "'.'",
            TokenType.IDENTIFIER: "identifier",
            TokenType.NUMBER: "number",
            TokenType.STRING: "string",
            TokenType.BARE_STRING: "string",
            TokenType.COMPARISON_OPERATOR: "comparison operator",
            TokenType.NEWLINE: "newline",
            TokenType.EOF: "end of input",
        }

        return names.get(token_type, token_type.name.lower())