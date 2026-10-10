# Relational Algebra Grammar

## 1. EBNF Grammar

### 1.1 Lexical Elements

- LETTER ::= "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L" | "M" | "N" | "O" | "P" | "Q" | "R" | "S" | "T" | "U" | "V" | "W" | "X" | "Y" | "Z" | "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n" | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x" | "y" | "z" 

- DIGIT ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" 

- IDENT ::= LETTER { LETTER | DIGIT | "_" }

- NUMBER ::= [ "-" ] DIGIT { DIGIT }

- STRING ::= "'" { STRING_CHAR } "'"

- STRING_CHAR ::= NON_QUOTE_CHAR | "''"

- NEWLINE ::= line-ending character

- NON_QUOTE_CHAR ::= any character except "'" or a line-ending character

- BARE_STRING_CHAR ::= any character except ",", whitespace, "(", ")", "'", "{", or "}"

- BARE_STRING ::= BARE_STRING_CHAR { BARE_STRING_CHAR }

#### Lexical Conventions

- If an unquoted relation value matches `NUMBER`, it is tokenized as `NUMBER`; otherwise, it is tokenized as `BARE_STRING`.
- `{` and `}` are excluded from bare strings because they delimit relation definitions. A string containing either brace must therefore be quoted.
- Spaces and tabs outside of quoted strings are ignored by the tokenizer.
- `//` begins a comment. The tokenizer ignores all characters from `//` to the end of the current line.
- Empty lines are ignored by the tokenizer.
- Outside relation definitions, newline characters are ignored.
- Inside relation definitions, a newline following relation data is emitted as a `NEWLINE` token because it separates tuples. Blank lines inside relation definitions do not produce `NEWLINE` tokens.
- The tokenizer uses maximal munch, choosing the longest valid token when multiple tokens could match the input. For example, `>=`, `<=`, and `!=` are recognized as single comparison operators.
- Keywords can be interpreted as identifiers when the grammar expects an identifier.


### 1.2 Relation Definitions

- ATTRIBUTE_NAME_LIST ::= IDENT { "," IDENT }

- ATTRIBUTE_LIST ::= ATTRIBUTE { "," ATTRIBUTE }

- RELATION_VALUE ::= NUMBER | STRING | BARE_STRING

- VALUE_LIST ::= RELATION_VALUE { "," RELATION_VALUE }

- TUPLE ::= VALUE_LIST

- RELATION_DEFINITION ::= IDENT "(" ATTRIBUTE_NAME_LIST ")" "=" "{" NEWLINE { TUPLE NEWLINE } "}"

### 1.3 Relational Expressions

- SELECT_EXPR ::= "select" "[" CONDITION "]" "(" EXPR ")"

- PROJECT_EXPR ::= "project" "[" ATTRIBUTE_LIST "]" "(" EXPR ")"

- RENAME_EXPR ::= "rename" "[" IDENT "]" "(" EXPR ")"

- EXPR ::= SET_EXPR

- SET_EXPR ::= PRODUCT_EXPR { ( "union" | "intersect" | "minus"  ) PRODUCT_EXPR }

- PRODUCT_EXPR ::= PRIMARY_EXPR { ( "times" | "join" "[" CONDITION "]" ) PRIMARY_EXPR }

- PRIMARY_EXPR ::= IDENT | PROJECT_EXPR | SELECT_EXPR | RENAME_EXPR | SORT_EXPR | "(" EXPR ")"

- SORT_DIRECTION ::= "asc" | "desc"

- SORT_EXPR ::= "sort" "[" ATTRIBUTE SORT_DIRECTION "]" "(" EXPR ")"

### 1.4 Conditions

- CONDITION ::= OR_CONDITION

- OR_CONDITION ::= AND_CONDITION { "or" AND_CONDITION } 

- AND_CONDITION ::= NOT_CONDITION { "and" NOT_CONDITION }

- NOT_CONDITION ::= "not" NOT_CONDITION | CONDITION_PRIMARY

- COMPARISON_OPERATOR ::= "=" | ">" | "<" | ">=" | "<=" | "!="

- COMPARISON ::= OPERAND COMPARISON_OPERATOR OPERAND

- ATTRIBUTE ::= IDENT [ "." IDENT ]

- OPERAND ::= NUMBER | STRING | ATTRIBUTE

- CONDITION_PRIMARY ::= "(" CONDITION ")" | COMPARISON

### 1.5 Semantic Constraints

- The grammar describes the syntactic structure of relational algebra expressions. Some restrictions are checked during semantic analysis rather than parsing.

- For projection, each attribute may appear at most once in the projection list. A duplicate attribute is a semantic error. For example: `project[Name, Name](R)`

- is syntactically valid according to the grammar but produces a semantic error because `Name` appears more than once in the projection list.

## 2. Precedence and Associativity

Relational operators follow the following precedence, from highest to lowest:

| Precedence | Operators | Associativity | Grammar Rule |
|---|---|---|---|
| 1 (highest) | `select`, `project`, `rename`, `sort` | N/A | `PRIMARY_EXPR` |
| 2 | `times`, `join[condition]` | Left | `PRODUCT_EXPR` |
| 3 (lowest) | `union`, `intersect`, `minus` | Left | `SET_EXPR` |

The unary operators `select`, `project`, `rename`, and `sort` have their scope explicitly determined by the expression enclosed in their parentheses, so associativity does not apply to them.

The `PRODUCT_EXPR` rule gives `times` and `join` higher precedence than the set operators. The `SET_EXPR` rule places `union`, `intersect`, and `minus` at the lower precedence level. Repetition using `{ ... }` causes operators at the same level to be grouped from left to right by the parser.

For example:

`R union S times T`

is interpreted as:

`R union (S times T)`

and:

`R minus S minus T`

is interpreted as:

`(R minus S) minus T`

Operators inside conditions follow the following precedence, from highest to lowest:

| Precedence | Operators | Associativity | Grammar Rule |
|---|---|---|---|
| 1 (highest) | `=`, `!=`, `<`, `<=`, `>`, `>=` | N/A | `COMPARISON` |
| 2 | `not` | Right | `NOT_CONDITION` |
| 3 | `and` | Left | `AND_CONDITION` |
| 4 (lowest) | `or` | Left | `OR_CONDITION` |

Comparison operators form a `COMPARISON` between two operands and are non-associative. The recursive `NOT_CONDITION` rule gives `not` the next-highest precedence and allows repeated negation. The `AND_CONDITION` and `OR_CONDITION` rules use repetition to enforce their respective precedence levels and left associativity.

For example:

`not a=1 and b=2 or c=3`

is interpreted as:

`((not (a=1)) and (b=2)) or (c=3)`

Parentheses override the normal precedence rules. For example:

`(a=1 or b=2) and c=3`

evaluates the parenthesized `or` condition before the `and`.

## 3. Ambiguity Demonstration

Consider the following naive grammar:

Expr ::= Expr "union" Expr
       | Expr "minus" Expr
       | "(" Expr ")"
       | IDENT

This grammar is ambiguous because the same input can produce more than one valid parse tree.

For example, consider:

`A union B minus C`

There are two possible interpretations:

`(A union B) minus C`

and:

`A union (B minus C)`

The first interpretation produces the following parse tree:

        minus
       /     \
    union     C
   /     \
  A       B

The second interpretation produces a different parse tree:

       union
      /     \
     A      minus
           /     \
          B       C

Therefore, the naive grammar is ambiguous because the same input can be represented by two different parse trees.

### Concrete Example

Consider three union-compatible relations, each with a single attribute `x`:

A(x) = { 1 }

B(x) = { 2 }

C(x) = { 1 }

Using the first parse tree:

`(A union B) minus C`

we get:

`({ 1 } union { 2 }) minus { 1 }`

`= { 1, 2 } minus { 1 }`

`= { 2 }`

Using the second parse tree:

`A union (B minus C)`

we get:

`{ 1 } union ({ 2 } minus { 1 })`

`= { 1 } union { 2 }`

`= { 1, 2 }`

The two parse trees therefore produce different results:

`(A union B) minus C = { 2 }`

`A union (B minus C) = { 1, 2 }`

### Removing the Ambiguity

The grammar removes this ambiguity by separating relational expressions into precedence levels:

EXPR ::= SET_EXPR

SET_EXPR ::= PRODUCT_EXPR { ( "union" | "intersect" | "minus" ) PRODUCT_EXPR }

PRODUCT_EXPR ::= PRIMARY_EXPR { ( "times" | "join" "[" CONDITION "]" ) PRIMARY_EXPR }

PRIMARY_EXPR ::= IDENT | PROJECT_EXPR | SELECT_EXPR | RENAME_EXPR | SORT_EXPR | "(" EXPR ")"

The `SET_EXPR` rule places `union`, `intersect`, and `minus` at the same precedence level. These operators are parsed from left to right, making them left-associative.

Therefore:

`A union B minus C`

is forced to group as:

`(A union B) minus C`

and produces the first parse tree:

        minus
       /     \
    union     C
   /     \
  A       B

### Associativity Example

Associativity can also create ambiguity. Consider:

`R minus S minus T`

Without an associativity rule, this could be interpreted as either:

`(R minus S) minus T`

or:

`R minus (S minus T)`

Consider three union-compatible relations:

R(x) = { 1, 2 }

S(x) = { 2 }

T(x) = { 1 }

Using left associativity:

`(R minus S) minus T`

we get:

`({ 1, 2 } minus { 2 }) minus { 1 }`

`= { 1 } minus { 1 }`

`= { }`

Using right associativity:

`R minus (S minus T)`

we get:

`{ 1, 2 } minus ({ 2 } minus { 1 })`

`= { 1, 2 } minus { 2 }`

`= { 1 }`

The two groupings therefore produce different results:

`(R minus S) minus T = { }`

`R minus (S minus T) = { 1 }`

The grammar resolves this ambiguity using the rule:

`SET_EXPR ::= PRODUCT_EXPR { ( "union" | "intersect" | "minus" ) PRODUCT_EXPR }`

Operators at this level are parsed from left to right. Therefore, `minus` is left-associative and:

`R minus S minus T`

is interpreted as:

`(R minus S) minus T`

## 4. Parsing Strategy

The parser uses a recursive-descent parsing strategy, with parsing functions corresponding to the major non-terminals in the EBNF grammar. Recursive descent was chosen because the stratified grammar maps naturally to separate parsing functions for each non-terminal and precedence level, making the parser straightforward to implement by hand using token lookahead without requiring a parser generator.

Separate parsing functions are used for each precedence level. Relational expressions follow this structure:

`parseExpr() → parseSetExpr() → parseProductExpr() → parsePrimaryExpr()`

This ensures that `times` and `join` are parsed before `union`, `intersect`, and `minus`.

Conditions use the same strategy:

`parseCondition() → parseOrCondition() → parseAndCondition() → parseNotCondition() → parseConditionPrimary() → parseComparison()`

This ensures that Boolean operators follow the precedence `not`, then `and`, then `or`.

Repeated binary operators at the same precedence level are parsed iteratively from left to right. The parser maintains an accumulated left-hand expression and combines it with each subsequent operator and right-hand expression. This produces the left associativity defined by the grammar.

For example:

`R minus S minus T`

is constructed as:

`(R minus S) minus T`

When `parsePrimaryExpr()` encounters an opening parenthesis, it consumes the `(` and recursively calls `parseExpr()` to parse the expression inside. It then requires a matching `)`. This allows parentheses to override normal operator precedence and supports nested parenthesized expressions.

The parser uses token lookahead to inspect the current token and determine which grammar production should be parsed. Tokens are consumed as they are successfully matched. For example, `parsePrimaryExpr()` uses the current token to determine whether it should parse an identifier, selection, projection, rename operation, sort operation, or parenthesized expression.

If the parser encounters a token that does not match what is required by the grammar, it reports a syntax error identifying the unexpected token and, when possible, the expected token or construct. For example:

`select[a=1(R)`

would produce a syntax error because the parser expects `]` after the condition but encounters `(` instead.

### Left Recursion

Left recursion must be avoided when using a recursive-descent parser. For example, the naive rule:

`Expr ::= Expr "union" Expr`

is left-recursive because parsing `Expr` requires parsing another `Expr` before any input is consumed. A recursive-descent implementation of this rule could repeatedly call `parseExpr()` without advancing through the input, eventually causing a stack overflow.

The grammar avoids this problem by replacing the left-recursive structure with precedence levels and EBNF repetition. For example:

`EXPR ::= SET_EXPR`

`SET_EXPR ::= PRODUCT_EXPR { ( "union" | "intersect" | "minus" ) PRODUCT_EXPR }`

`PRODUCT_EXPR ::= PRIMARY_EXPR { ( "times" | "join" "[" CONDITION "]" ) PRIMARY_EXPR }`

Here, `SET_EXPR` first parses a `PRODUCT_EXPR`, which in turn first parses a `PRIMARY_EXPR`. This allows the parser to consume an operand before processing any repeated binary operators. The `{ ... }` repetition can then be processed iteratively from left to right without recursively calling `parseSetExpr()`.

The condition grammar avoids left recursion in the same way. For example:

`OR_CONDITION ::= AND_CONDITION { "or" AND_CONDITION }`

first parses an `AND_CONDITION` before processing repeated `or` operators. The rule:

`NOT_CONDITION ::= "not" NOT_CONDITION | CONDITION_PRIMARY`

is recursive but not left-recursive because the `"not"` token is consumed before the recursive call. This makes progress through the input and allows repeated `not` operators to be parsed right-associatively.

## 5. Sources

- COMP 3005 Bonus Assignment 1 specification. Used as the primary reference for the required relational algebra syntax, relation definitions, operators, lexical rules, precedence, and parsing requirements.

- Pattis, Richard E. "Teaching EBNF First in CS 1." SIGCSE '94, Association for Computing Machinery, 1994. Used as a reference for EBNF notation, including sequence, choice, optional elements, repetition, and recursion.

- Scott, Elizabeth, and Adrian Johnstone. "GLL Parsing." Electronic Notes in Theoretical Computer Science, vol. 253, 2010, pp. 177–189. Used as a reference for the recursive-descent parsing approach, particularly the use of parsing functions corresponding to grammar non-terminals.

### AI Assistance and Corrections

AI assistance was used while developing and reviewing the grammar. AI-generated suggestions were manually checked against the assignment requirements and tested before being accepted. Several suggestions were found to be incorrect or incomplete and were corrected during development.

1. **Incorrect ambiguity example**

   While constructing the concrete ambiguity example for `A union B minus C`, the AI initially suggested:

   `A = { 1 }`, `B = { 2 }`, `C = { 2 }`

   However, manually evaluating both parse trees showed:

   `(A union B) minus C = { 1 }`

   `A union (B minus C) = { 1 }`

   Since both interpretations produced the same result, the example did not demonstrate why the ambiguity matters. The relations were corrected to:

   `A = { 1 }`, `B = { 2 }`, `C = { 1 }`

   With the corrected relations:

   `(A union B) minus C = { 2 }`

   `A union (B minus C) = { 1, 2 }`

   This demonstrated that the two valid parse trees can produce different relational results.

2. **Missing support for bare string values**

   An earlier AI-assisted version of the grammar treated relation values as only `NUMBER` or quoted `STRING` values. This was incomplete because relation definitions also need to support unquoted string values such as `E1`, `John`, and `D1`.

   The grammar was corrected by introducing `BARE_STRING` and changing the relation value rule to:

   `RELATION_VALUE ::= NUMBER | STRING | BARE_STRING`

   This allows relation definitions to contain both quoted strings and valid unquoted string values.

3. **Incorrect construction of `BARE_STRING`**

   An earlier AI suggestion attempted to construct bare strings using `LETTER` and `NUMBER`. This was incorrect because `NUMBER` represents a complete numeric token rather than a single character. For example:

   `NUMBER ::= [ "-" ] DIGIT { DIGIT }`

   can represent values such as `1`, `42`, or `-7`, so it should not be used as an individual character when defining a bare string.

   The grammar was corrected by defining a character-level rule:

   `BARE_STRING_CHAR ::= any character except ",", whitespace, "(", ")", "'", "{", or "}"`

   `BARE_STRING ::= BARE_STRING_CHAR { BARE_STRING_CHAR }`

   This separates the definition of an allowed bare-string character from the definition of a complete numeric token.