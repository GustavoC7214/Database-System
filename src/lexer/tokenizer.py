from .token import SourcePosition, Token, TokenType


class LexicalError(Exception):
    pass


class Tokenizer:
    def __init__(self, source: str):
        self.source = source

        self.start = SourcePosition(index=0, line=1, column=1)
        self.current = SourcePosition(index=0, line=1, column=1)

        self.tokens: list[Token] = []
        self.inside_relation_data = False
        self.line_has_data = False
        self.single_char_tokens = {
            '(': TokenType.LPAREN,
            ')': TokenType.RPAREN,
            '[': TokenType.LBRACKET,
            ']': TokenType.RBRACKET,
            ',': TokenType.COMMA,
            '.': TokenType.DOT
        }

    def is_at_end(self) -> bool:
        return self.current.index >= len(self.source)

    def current_char(self) -> str | None:
        if self.is_at_end():
            return None
        else:
            return self.source[self.current.index]

    def advance(self) -> str | None:
        char = self.current_char()

        if char is None:
            return None
        
        self.current.index += 1

        if char == '\n':
            self.current.line += 1
            self.current.column = 1
        else:
            self.current.column += 1

        return char

    def next_char(self) -> str | None:
        if self.current.index + 1 >= len(self.source):
            return None
        else:
            return self.source[self.current.index + 1]

    def mark_start(self) -> None:
        self.start = SourcePosition(
            index=self.current.index,
            line=self.current.line,
            column=self.current.column
        )

    def tokenize(self) -> list[Token]:
        while not self.is_at_end():
            self.mark_start()
            self.scan_token()

        self.mark_start()
        self.add_token(TokenType.EOF)
        return self.tokens

    def add_token(self, token_type: TokenType, value: str | None = None) -> None:
        if value is None:
            value = self.source[self.start.index:self.current.index]

        token = Token(
            type=token_type,
            value=value,
            position=SourcePosition(
                index=self.start.index,
                line=self.start.line,
                column=self.start.column
            )
        )
        self.tokens.append(token)

    def scan_token(self) -> None:
        char = self.advance()

        if char is None:
            return

        if char == "/" and self.current_char() == "/":
            self.skip_comment()
            return

        if self.inside_relation_data and self.scan_relation_data_token(char):
            return
        if self.is_ascii_letter(char):
            self.scan_identifier()   
            
        elif char in self.single_char_tokens:
            self.add_token(self.single_char_tokens[char])
        elif char == "{":
            self.inside_relation_data = True
            self.line_has_data = True
            self.add_token(TokenType.LBRACE)
        elif char == "}":
            self.inside_relation_data = False
            self.line_has_data = False
            self.add_token(TokenType.RBRACE)
        elif char in ("=", ">", "<", "!"):
            self.scan_comparison_operator(char)
        elif char in (" ", "\t"):
            return  # Ignore whitespace
        elif char == "\n":
            self.handle_newline()
        elif self.scan_number_token(char):
            return
        elif char == "'":
            self.scan_string()
        else:
            raise LexicalError(
                f"Unexpected character '{char}' at line {self.start.line}, "
                f"column {self.start.column}"
            )

    def scan_identifier(self) -> None:
        while not self.is_at_end():
            char = self.current_char()

            if char is None or not (
                self.is_ascii_letter(char)
                or self.is_ascii_digit(char)
                or char == "_"
                ):
                break

            self.advance()
        self.add_token(TokenType.IDENTIFIER)

    def scan_comparison_operator(self, char: str) -> None:
        if char == "=":
            self.add_token(TokenType.COMPARISON_OPERATOR)
        elif char in (">", "<"):
            if self.current_char() == "=":
                self.advance()
            self.add_token(TokenType.COMPARISON_OPERATOR)
        elif char == "!" and self.current_char() == "=":
            self.advance()
            self.add_token(TokenType.COMPARISON_OPERATOR)
        else:
            raise LexicalError(
                f"Unexpected character '{char}' at line {self.start.line}, "
                f"column {self.start.column}"
            )

    def scan_number(self) -> None:
        while not self.is_at_end():
            char = self.current_char()

            if char is None or not self.is_ascii_digit(char):
                break
            self.advance()

        self.add_token(TokenType.NUMBER)

    def scan_string(self) -> None:
        terminated = False
        while not self.is_at_end():
            char = self.current_char()

            if char is None:
                break

            if char == "\n":
                raise LexicalError(
                    f"Unterminated string at line {self.start.line}, "
                    f"column {self.start.column}"
                )

            if char == "'" and self.next_char() == "'":
                self.advance()
                self.advance()  # Skip the escaped quote
                continue
            elif char == "'":
                self.advance()  # Consume the closing quote
                terminated = True
                break
            
            self.advance()
        
        if not terminated:
            raise LexicalError(
                f"Unterminated string at line {self.start.line}, "
                f"column {self.start.column}"
            )
        
        value = self.source[self.start.index + 1:self.current.index - 1]
        value = value.replace("''", "'")
        self.add_token(TokenType.STRING, value)

        if self.inside_relation_data:
            self.line_has_data = True

    def is_relation_value_delimiter(self, char: str) -> bool:
        return char in (",", "{", "}", "(", ")", "'") or char.isspace()

    def scan_relation_value(self) -> None:
        while not self.is_at_end():
            char = self.current_char()

            if char is None or self.is_relation_value_delimiter(char):
                break

            if (char == "/"
                and self.current.index + 1 < len(self.source)
                and self.source[self.current.index:self.current.index + 2] == "//"
                ):
                    break

            self.advance()
    
        value = self.source[self.start.index:self.current.index]
        if self.is_number_value(value):
            self.add_token(TokenType.NUMBER, value)
        else:
            self.add_token(TokenType.BARE_STRING, value)

    def scan_relation_data_token(self, char: str) -> bool:
        if not self.is_relation_value_delimiter(char):
            self.scan_relation_value()
            self.line_has_data = True
            return True
        
        return False

    def scan_number_token(self, char: str) -> bool:
        if self.is_ascii_digit(char):
            self.scan_number()
            return True

        if char == "-":
            next_char = self.current_char()
            if next_char is not None and self.is_ascii_digit(next_char):
                self.scan_number()
                return True

        return False

    def skip_comment(self) -> None:
        while not self.is_at_end() and self.current_char() != "\n":
            self.advance()

    def handle_newline(self) -> None:
        if self.inside_relation_data and self.line_has_data:
            self.add_token(TokenType.NEWLINE)
            self.line_has_data = False

    def is_ascii_letter(self, char: str) -> bool:
        return ("A" <= char <= "Z") or ("a" <= char <= "z")

    def is_ascii_digit(self, char: str) -> bool:
        return "0" <= char <= "9"

    def is_number_value(self, value: str) -> bool:
        value = value.removeprefix("-")  # Remove leading '-' for negative numbers

        return len(value) > 0 and all(self.is_ascii_digit(char) for char in value)
