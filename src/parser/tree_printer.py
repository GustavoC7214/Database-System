from src.parser.ast import (
    ASTNode,
    AttributeReference,
    BinaryExpression,
    BinaryOperator,
    BooleanBinaryCondition,
    BooleanOperator,
    Comparison,
    ComparisonOperator,
    Join,
    Not,
    NumberLiteral,
    Project,
    RelationReference,
    Rename,
    Select,
    Sort,
    StringLiteral,
)

COMPARISON_NAMES = {
    ComparisonOperator.EQUAL: "Eq",
    ComparisonOperator.NOT_EQUAL: "Ne",
    ComparisonOperator.LESS_THAN: "Lt",
    ComparisonOperator.LESS_THAN_OR_EQUAL: "Le",
    ComparisonOperator.GREATER_THAN: "Gt",
    ComparisonOperator.GREATER_THAN_OR_EQUAL: "Ge",
}

BOOLEAN_NAMES = {
    BooleanOperator.AND: "And",
    BooleanOperator.OR: "Or",
}

BINARY_NAMES = {
    BinaryOperator.UNION: "Union",
    BinaryOperator.INTERSECT: "Intersect",
    BinaryOperator.MINUS: "Minus",
    BinaryOperator.TIMES: "Times",
}


def print_tree(node: ASTNode) -> str:
    root_line = format_expression(node)
    children = get_children(node)
    lines = [root_line]

    for i, child in enumerate(children):
        child_is_last = i == len(children) - 1
        child_lines = print_node(child, "", child_is_last)
        lines.extend(child_lines)

    return "\n".join(lines)


def print_node(node: ASTNode, prefix: str, is_last: bool) -> list[str]:
    node_text = format_expression(node)
    branch = "└── " if is_last else "├── "
    line = prefix + branch + node_text

    child_prefix = prefix + ("    " if is_last else "│   ")
    children = get_children(node)
    lines = [line]

    for i, child in enumerate(children):
        child_is_last = i == len(children) - 1
        child_lines = print_node(child, child_prefix, child_is_last)
        lines.extend(child_lines)
    
    return lines


def format_inline(node: ASTNode) -> str:
    if isinstance(node, AttributeReference):
        if node.relation is None:
            return f"Attr({node.name})"
        else:
            return f"Attr({node.relation}.{node.name})"
    elif isinstance(node, NumberLiteral):
        return f"Num({node.value})"
    elif isinstance(node, StringLiteral):
        return f"Str('{node.value}')"
    elif isinstance(node, Comparison):
        left = format_inline(node.left)
        right = format_inline(node.right)
        operator = COMPARISON_NAMES[node.operator]
        return f"{operator}({left}, {right})"
    elif isinstance(node, BooleanBinaryCondition):
        left = format_inline(node.left)
        right = format_inline(node.right)
        operator = BOOLEAN_NAMES[node.operator]
        return f"{operator}({left}, {right})"
    elif isinstance(node, Not):
        condition = format_inline(node.condition)
        return f"Not({condition})"
    
    raise TypeError(f"Unsupported inline AST node: {type(node).__name__}")


def format_expression(node: ASTNode) -> str:
    if isinstance(node, RelationReference):
        return f"Relation({node.name})"
    elif isinstance(node, Select):
        condition = format_inline(node.condition)
        return f"Select(cond={condition})"
    elif isinstance(node, Project):
        attributes = ", ".join(format_attribute_name(attr) for attr in node.attributes)
        return f"Project(attrs=[{attributes}])"
    elif isinstance(node, BinaryExpression):
        operator = BINARY_NAMES[node.operator]
        return operator
    elif isinstance(node, Rename):
        return f"Rename(name={node.new_name})"
    elif isinstance(node, Sort):
        attribute = format_attribute_name(node.attribute)
        return f"Sort(attr={attribute}, direction={node.direction.value})"
    elif isinstance(node, Join):
        condition = format_inline(node.condition)
        return f"Join(cond={condition})"


    raise TypeError(f"Unsupported inline AST node: {type(node).__name__}")


def get_children(node: ASTNode) -> list[ASTNode]:
    if isinstance(node, RelationReference):
        return []
    elif isinstance(node, (Select, Project, Rename, Sort)):
        return [node.expression]
    elif isinstance(node, (BinaryExpression, Join)):
        return [node.left, node.right]

    raise TypeError(f"Unsupported inline AST node: {type(node).__name__}")


def format_attribute_name(attribute: AttributeReference) -> str:
    if attribute.relation is None:
        return attribute.name
    else:
        return f"{attribute.relation}.{attribute.name}"