import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from src.parser import ast

NODE_TYPES = {
    cls.__name__: cls
    for cls in vars(ast).values()
    if (
        isinstance(cls, type)
        and issubclass(cls, ast.ASTNode)
        and cls not in (ast.ASTNode, ast.Expression, ast.Condition, ast.Operand)
    )
}

ENUM_TYPES = {
    cls.__name__: cls
    for cls in vars(ast).values()
    if isinstance(cls, type)
    and issubclass(cls, Enum)
    and cls is not Enum
}


def ast_to_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return {
            "__enum__": type(value).__name__,
            "value": value.value,
        }

    if isinstance(value, ast.ASTNode) and is_dataclass(value):
        return {
            "__type__": type(value).__name__,
            **{
                field.name: ast_to_dict(getattr(value, field.name))
                for field in fields(value)
            },
        }

    if isinstance(value, list):
        return [ast_to_dict(item) for item in value]

    if isinstance(value, dict):
        return {
            key: ast_to_dict(item)
            for key, item in value.items()
        }

    if value is None or type(value) in (str, int, bool):
        return value

    raise TypeError(f"Cannot serialize value of type {type(value).__name__}")


def ast_from_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [ast_from_dict(item) for item in value]

    if isinstance(value, dict):
        if "__enum__" in value:
            enum_name = value["__enum__"]
            if enum_name not in ENUM_TYPES:
                raise ValueError(f"Unknown enum type: {enum_name}")
            return ENUM_TYPES[enum_name](value["value"])

        if "__type__" in value:
            node_name = value["__type__"]
            if node_name not in NODE_TYPES:
                raise ValueError(f"Unknown AST node type: {node_name}")

            node_class = NODE_TYPES[node_name]

            if not is_dataclass(node_class):
                raise TypeError(
                    f"AST node {node_name} is not a dataclass"
                )

            arguments = {
                field.name: ast_from_dict(value[field.name])
                for field in fields(node_class)
            }

            return node_class(**arguments)

        return {
            key: ast_from_dict(item)
            for key, item in value.items()
        }

    return value


def ast_to_json(node: ast.ASTNode) -> str:
    return json.dumps(ast_to_dict(node), indent=2)


def ast_from_json(text: str) -> ast.ASTNode:
    result = ast_from_dict(json.loads(text))

    if not isinstance(result, ast.ASTNode):
        raise TypeError("JSON does not contain an AST node")

    return result