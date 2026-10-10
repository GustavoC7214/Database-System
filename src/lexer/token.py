from dataclasses import dataclass
from enum import Enum


class TokenType(Enum):
    # Single-character tokens
    LPAREN = '('
    RPAREN = ')'
    LBRACE = '{'
    RBRACE = '}'
    LBRACKET = '['
    RBRACKET = ']'
    COMMA = ','
    DOT = '.'
    
    # Comparison operators
    COMPARISON_OPERATOR = 'COMPARISON_OPERATOR'

    # Literals
    IDENTIFIER = 'IDENTIFIER'
    STRING = 'STRING'
    NUMBER = 'NUMBER'
    BARE_STRING = 'BARE_STRING'

    #Special tokens
    NEWLINE = 'NEWLINE'
    EOF = 'EOF'

@dataclass
class SourcePosition:
    index: int
    line: int
    column: int
    
@dataclass
class Token:
    type: TokenType
    value: str
    position: SourcePosition