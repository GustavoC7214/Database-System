"""Semantics-preserving logical-plan rewrites for Module 4.

Phase 3A:
- Split conjunctive selections.
- Push single-input predicates below joins and cross products.
- Convert cross products with equality predicates into joins.

Input and output use the Module 3 logical JSON plan format.
"""

from copy import deepcopy
from typing import Any

from src.optimizer.predicates import (
    BooleanPredicate,
    ColumnRef,
    ComparisonPredicate,
    LiteralValue,
    NotPredicate,
    Predicate,
    parse_predicate,
)

Plan = dict[str, Any]


def _render_operand(value: ColumnRef | LiteralValue) -> str:
    if isinstance(value, ColumnRef):
        return value.name
    if isinstance(value.value, str):
        return "'" + value.value.replace("'", "''") + "'"
    return str(value.value)


def render_predicate(predicate: Predicate) -> str:
    """Render a predicate in the Module 3 compiler's condition syntax."""
    if isinstance(predicate, ComparisonPredicate):
        return (
            f"{_render_operand(predicate.left)} "
            f"{predicate.operator} "
            f"{_render_operand(predicate.right)}"
        )
    if isinstance(predicate, NotPredicate):
        return f"NOT ({render_predicate(predicate.operand)})"
    if isinstance(predicate, BooleanPredicate):
        return (
            f"({render_predicate(predicate.left)} "
            f"{predicate.operator} "
            f"{render_predicate(predicate.right)})"
        )
    raise TypeError(f"Unsupported predicate: {predicate!r}")


def split_conjunction(predicate: Predicate) -> list[Predicate]:
    """Return AND components in left-to-right order."""
    if isinstance(predicate, BooleanPredicate) and predicate.operator == "AND":
        return split_conjunction(predicate.left) + split_conjunction(predicate.right)
    return [predicate]


def referenced_columns(predicate: Predicate) -> set[str]:
    """Collect all column references, including those inside NOT/OR."""
    if isinstance(predicate, ComparisonPredicate):
        return {
            operand.name
            for operand in (predicate.left, predicate.right)
            if isinstance(operand, ColumnRef)
        }
    if isinstance(predicate, NotPredicate):
        return referenced_columns(predicate.operand)
    if isinstance(predicate, BooleanPredicate):
        return referenced_columns(predicate.left) | referenced_columns(predicate.right)
    raise TypeError(f"Unsupported predicate: {predicate!r}")


def _output_columns(
    plan: Plan,
    table_columns: dict[str, list[str]],
) -> set[str] | None:
    """Determine available output columns, or None when unknown.

    Unknown schemas are never used to justify pushing a predicate.
    """
    op = plan["op"]

    if op == "scan":
        table = plan["table"]
        names = table_columns.get(table)
        if names is None:
            return None
        return {f"{table}.{name}" for name in names}

    if op == "rename":
        child = _output_columns(plan["child"], table_columns)
        if child is None:
            return None
        return {f"{plan['to']}.{name.rsplit('.', 1)[-1]}" for name in child}

    if op == "project":
        columns = plan["columns"]
        outputs = plan.get("outputs", columns)
        return set(outputs)

    if op == "group_by":
        return set(plan.get("keys", [])) | {
            aggregate[2] for aggregate in plan.get("aggregates", [])
        }

    if op in {"select", "sort", "distinct", "limit"}:
        return _output_columns(plan["child"], table_columns)

    if op in {"cross", "join"}:
        left = _output_columns(plan["left"], table_columns)
        right = _output_columns(plan["right"], table_columns)
        if left is None or right is None:
            return None
        return left | right

    if op in {"union", "union_all", "intersect", "except"}:
        return _output_columns(plan["left"], table_columns)

    return None


def _contains_reference(
    reference: str,
    columns: set[str] | None,
) -> bool:
    if columns is None:
        return False

    if reference in columns:
        return True

    if "." in reference:
        return False

    return sum(name.rsplit(".", 1)[-1] == reference for name in columns) == 1


def _side_for(
    predicate: Predicate,
    left: set[str] | None,
    right: set[str] | None,
) -> str | None:
    """Return a side only if every reference belongs exclusively to it."""
    references = referenced_columns(predicate)
    if not references:
        return None

    side: str | None = None

    for reference in references:
        in_left = _contains_reference(reference, left)
        in_right = _contains_reference(reference, right)

        if in_left == in_right:
            return None

        current = "left" if in_left else "right"
        if side is not None and side != current:
            return None
        side = current

    return side


def _is_cross_equality(
    predicate: Predicate,
    left: set[str] | None,
    right: set[str] | None,
) -> bool:
    """Recognize an equijoin predicate connecting opposite inputs."""
    if not isinstance(predicate, ComparisonPredicate):
        return False
    if predicate.operator not in {"=", "=="}:
        return False
    if not isinstance(predicate.left, ColumnRef):
        return False
    if not isinstance(predicate.right, ColumnRef):
        return False

    left_side = _side_for(
        ComparisonPredicate(predicate.left, "=", predicate.left),
        left,
        right,
    )
    right_side = _side_for(
        ComparisonPredicate(predicate.right, "=", predicate.right),
        left,
        right,
    )
    return left_side is not None and right_side is not None and left_side != right_side


def _select(condition: str, child: Plan) -> Plan:
    return {
        "op": "select",
        "condition": condition,
        "child": child,
    }


def _attach_predicates(
    child: Plan,
    predicates: list[Predicate],
) -> Plan:
    """Attach predicates while preserving their original order."""
    for predicate in predicates:
        child = _select(render_predicate(predicate), child)
    return child


def _replace_columns(
    predicate: Predicate,
    replacements: dict[str, str],
) -> Predicate:
    """Return a predicate with column references renamed."""
    if isinstance(predicate, ComparisonPredicate):

        def replace_operand(
            operand: ColumnRef | LiteralValue,
        ) -> ColumnRef | LiteralValue:
            if isinstance(operand, ColumnRef):
                return ColumnRef(replacements.get(operand.name, operand.name))
            return operand

        return ComparisonPredicate(
            replace_operand(predicate.left),
            predicate.operator,
            replace_operand(predicate.right),
        )

    if isinstance(predicate, NotPredicate):
        return NotPredicate(_replace_columns(predicate.operand, replacements))

    if isinstance(predicate, BooleanPredicate):
        return BooleanPredicate(
            predicate.operator,
            _replace_columns(predicate.left, replacements),
            _replace_columns(predicate.right, replacements),
        )

    raise TypeError(f"Unsupported predicate: {predicate!r}")


def _combine_predicates(
    predicates: list[Predicate],
) -> Predicate:
    """Combine predicates into a deterministic AND expression."""
    if not predicates:
        raise ValueError("Cannot combine an empty predicate list")

    combined = predicates[0]
    for predicate in predicates[1:]:
        combined = BooleanPredicate("AND", combined, predicate)
    return combined


def _push_through_rename(
    predicate: Predicate,
    rename: Plan,
    table_columns: dict[str, list[str]],
) -> Predicate | None:
    """Translate alias-qualified references into child column names."""
    child_columns = _output_columns(rename["child"], table_columns)
    if child_columns is None:
        return None

    alias = rename["to"]
    replacements: dict[str, str] = {}

    for reference in referenced_columns(predicate):
        if "." in reference:
            qualifier, name = reference.rsplit(".", 1)
            if qualifier != alias:
                return None
        else:
            name = reference

        matches = [
            column for column in child_columns if column.rsplit(".", 1)[-1] == name
        ]
        if len(matches) != 1:
            return None

        replacements[reference] = matches[0]

    return _replace_columns(predicate, replacements)


def _push_through_group_by(
    predicate: Predicate,
    group: Plan,
) -> bool:
    """Only grouping-key predicates may move below aggregation."""
    references = referenced_columns(predicate)
    grouping_keys = set(group.get("keys", []))

    return bool(references) and references <= grouping_keys


def _push_through_union(
    predicate: Predicate,
    union: Plan,
    table_columns: dict[str, list[str]],
) -> bool:
    """Check that predicate names resolve identically in both inputs.

    This intentionally supports only identical output names.
    Position-based column translation is deferred to a later phase.
    """
    references = referenced_columns(predicate)
    if not references:
        return False

    left_columns = _output_columns(union["left"], table_columns)
    right_columns = _output_columns(union["right"], table_columns)

    if left_columns is None or right_columns is None:
        return False

    return all(
        reference in left_columns and reference in right_columns
        for reference in references
    )


def _rewrite_select(
    plan: Plan,
    table_columns: dict[str, list[str]],
) -> Plan:
    """Push selection predicates down as far as safely possible."""
    child = plan["child"]
    predicates = split_conjunction(parse_predicate(plan["condition"]))

    # Merge consecutive selections into one selection node.
    if child["op"] == "select":
        predicates = split_conjunction(parse_predicate(child["condition"])) + predicates

        merged = _select(
            render_predicate(_combine_predicates(predicates)),
            child["child"],
        )

        # If the next operator is a join, cross, rename, group_by,
        # or union, continue pushing the merged predicate downward.
        # Otherwise, retain the merged selection as one node.
        if merged["child"]["op"] in {
            "join",
            "cross",
            "rename",
            "group_by",
            "union",
            "union_all",
        }:
            return _rewrite_select(merged, table_columns)

        return merged

    # Translate alias references and push through a rename.
    if child["op"] == "rename":
        pushed: list[Predicate] = []
        remaining: list[Predicate] = []

        for predicate in predicates:
            translated = _push_through_rename(predicate, child, table_columns)
            if translated is None:
                remaining.append(predicate)
            else:
                pushed.append(translated)

        result = dict(child)
        if pushed:
            result["child"] = _rewrite(
                _attach_predicates(child["child"], pushed),
                table_columns,
            )

        return _attach_predicates(result, remaining)

    # A filter on grouping keys can be applied before aggregation.
    if child["op"] == "group_by":
        pushed = []
        remaining = []

        for predicate in predicates:
            if _push_through_group_by(predicate, child):
                pushed.append(predicate)
            else:
                remaining.append(predicate)

        result = dict(child)
        if pushed:
            result["child"] = _rewrite(
                _attach_predicates(child["child"], pushed),
                table_columns,
            )

        return _attach_predicates(result, remaining)

    # Distribute safe filters to both inputs of UNION/UNION ALL.
    if child["op"] in {"union", "union_all"}:
        pushed = []
        remaining = []

        for predicate in predicates:
            if _push_through_union(predicate, child, table_columns):
                pushed.append(predicate)
            else:
                remaining.append(predicate)

        result = dict(child)
        if pushed:
            result["left"] = _rewrite(
                _attach_predicates(child["left"], pushed),
                table_columns,
            )
            result["right"] = _rewrite(
                _attach_predicates(child["right"], pushed),
                table_columns,
            )

        return _attach_predicates(result, remaining)

    # Phase 3A: split and push predicates through joins/crosses.
    if child["op"] not in {"join", "cross"}:
        return _attach_predicates(child, predicates)

    left_columns = _output_columns(child["left"], table_columns)
    right_columns = _output_columns(child["right"], table_columns)

    left_filters: list[Predicate] = []
    right_filters: list[Predicate] = []
    join_filters: list[Predicate] = []
    remaining: list[Predicate] = []

    for predicate in predicates:
        side = _side_for(predicate, left_columns, right_columns)

        if side == "left":
            left_filters.append(predicate)
        elif side == "right":
            right_filters.append(predicate)
        elif child["op"] == "cross" and _is_cross_equality(
            predicate, left_columns, right_columns
        ):
            join_filters.append(predicate)
        else:
            remaining.append(predicate)

    result = dict(child)

    result["left"] = _rewrite(
        _attach_predicates(child["left"], left_filters),
        table_columns,
    )
    result["right"] = _rewrite(
        _attach_predicates(child["right"], right_filters),
        table_columns,
    )

    if join_filters:
        result["op"] = "join"
        result["condition"] = render_predicate(_combine_predicates(join_filters))

    return _attach_predicates(result, remaining)


def _rewrite(
    plan: Plan,
    table_columns: dict[str, list[str]],
) -> Plan:
    op = plan["op"]
    result = dict(plan)

    if "child" in plan:
        result["child"] = _rewrite(plan["child"], table_columns)

    if "left" in plan and "right" in plan:
        result["left"] = _rewrite(plan["left"], table_columns)
        result["right"] = _rewrite(plan["right"], table_columns)

    if op == "select":
        return _rewrite_select(result, table_columns)

    return result


def rewrite_plan(
    plan: Plan,
    *,
    table_columns: dict[str, list[str]] | None = None,
) -> Plan:
    """Return a rewritten logical plan without mutating the input.

    Supply schema column names to enable safe join-side classification.
    Unknown columns and ambiguous references are not pushed.
    """
    return _rewrite(
        deepcopy(plan),
        table_columns or {},
    )
