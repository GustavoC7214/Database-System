from src.engine.database import Database
from src.engine.evaluator import Evaluator
from src.engine.relation import Attribute, Relation, Row
from src.lexer.tokenizer import Tokenizer
from src.parser.ast import Expression, RelationDefinition
from src.parser.parser import Parser


class QueryProcessor:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.evaluator = Evaluator(database)

    def execute(self, source: str) -> Relation:
        tokens = Tokenizer(source).tokenize()
        ast = Parser(tokens).parse()

        if isinstance(ast, RelationDefinition):
            attributes = [
                Attribute(ast.name, name)
                for name in ast.attributes
            ]

            rows = [
                Row(values)
                for values in ast.rows
            ]

            relation = Relation(
                ast.name,
                attributes,
                rows,
            )

            self.database.add_relation(relation)
            return relation

        if isinstance(ast, Expression):
            return self.evaluator.evaluate(ast)

        raise TypeError(
            f"Unsupported AST node: {type(ast).__name__}"
        )