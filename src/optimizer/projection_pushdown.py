"""Conservative, dependency-aware logical projection pushdown."""

from copy import deepcopy
from typing import Any

from src.optimizer.predicates import parse_predicate
from src.optimizer.rewrites import referenced_columns

Plan = dict[str, Any]


def _columns(
    plan: Plan,
    schemas: dict[str, list[str]],
) -> list[str] | None:
    """Return ordered output names where they can be established."""
    op = plan["op"]

    if op == "scan":
        names = schemas.get(plan["table"])
        if names is None:
            return None
        return [f"{plan['table']}.{name}" for name in names]

    if op == "project":
        outputs = plan.get("outputs")
        if outputs is not None:
            return list(outputs)
        if plan.get("aliases"):
            return None
        return list(plan["columns"])

    if op == "rename":
        child = _columns(plan["child"], schemas)
        if child is None:
            return None
        return [f"{plan['to']}.{name.rsplit('.', 1)[-1]}" for name in child]

    if op in {"join", "cross"}:
        left = _columns(plan["left"], schemas)
        right = _columns(plan["right"], schemas)
        if left is None or right is None:
            return None
        return left + right

    if op in {"select", "sort", "limit", "distinct"}:
        return _columns(plan["child"], schemas)

    return None


def _resolve(
    reference: str,
    available: list[str],
) -> str | None:
    """Resolve a reference only when it has one unambiguous match."""
    if reference in available:
        return reference

    if "." in reference:
        return None

    matches = [column for column in available if column.rsplit(".", 1)[-1] == reference]
    return matches[0] if len(matches) == 1 else None


def _resolve_all(
    references: set[str],
    available: list[str],
) -> set[str] | None:
    resolved: set[str] = set()

    for reference in references:
        column = _resolve(reference, available)
        if column is None:
            return None
        resolved.add(column)

    return resolved


def _predicate_columns(condition: str) -> set[str]:
    return referenced_columns(parse_predicate(condition))


def _project_if_useful(
    child: Plan,
    required: set[str],
    schemas: dict[str, list[str]],
) -> Plan:
    available = _columns(child, schemas)

    if available is None or not required:
        return child

    if not required <= set(available):
        return child

    selected = [column for column in available if column in required]

    if len(selected) == len(available):
        return child

    return {
        "op": "project",
        "columns": selected,
        "child": child,
    }


def _push(
    plan: Plan,
    required: set[str],
    schemas: dict[str, list[str]],
) -> Plan:
    """Push required columns down through supported operators."""
    op = plan["op"]
    result = dict(plan)

    if op == "scan":
        return result

    if op == "select":
        available = _columns(plan["child"], schemas)
        if available is None:
            return result

        dependencies = _resolve_all(
            _predicate_columns(plan["condition"]),
            available,
        )
        if dependencies is None:
            return result

        needed = required | dependencies
        result["child"] = _push(plan["child"], needed, schemas)
        result["child"] = _project_if_useful(result["child"], needed, schemas)
        return result

    if op == "sort":
        available = _columns(plan["child"], schemas)
        if available is None:
            return result

        key_references = {key for key, _direction in plan["keys"]}
        dependencies = _resolve_all(key_references, available)
        if dependencies is None:
            return result

        needed = required | dependencies
        result["child"] = _push(plan["child"], needed, schemas)
        result["child"] = _project_if_useful(result["child"], needed, schemas)
        return result

    if op == "limit":
        result["child"] = _push(plan["child"], required, schemas)
        return result

    if op in {"join", "cross"}:
        left_columns = _columns(plan["left"], schemas)
        right_columns = _columns(plan["right"], schemas)

        if left_columns is None or right_columns is None:
            return result

        available = left_columns + right_columns

        # A duplicate output name cannot be assigned safely.
        if len(available) != len(set(available)):
            return result

        resolved = _resolve_all(required, available)
        if resolved is None:
            return result

        dependencies: set[str] = set()
        if op == "join":
            resolved_condition = _resolve_all(
                _predicate_columns(plan["condition"]),
                available,
            )
            if resolved_condition is None:
                return result
            dependencies = resolved_condition

        needed = resolved | dependencies
        left_needed = needed & set(left_columns)
        right_needed = needed & set(right_columns)

        result["left"] = _push(plan["left"], left_needed, schemas)
        result["right"] = _push(plan["right"], right_needed, schemas)

        result["left"] = _project_if_useful(result["left"], left_needed, schemas)
        result["right"] = _project_if_useful(result["right"], right_needed, schemas)
        return result

    # A boundary is left unchanged unless its semantics are known.
    return result


def push_projections(
    plan: Plan,
    *,
    table_columns: dict[str, list[str]] | None = None,
) -> Plan:
    """Optimize projection dependencies without mutating the input.

    An explicit root projection is required. Plans without one are
    returned unchanged because their full output may be observable.
    """
    result = deepcopy(plan)
    schemas = table_columns or {}

    if result["op"] != "project":
        return result

    # Aliased or computed output expressions need a separate
    # expression-to-source mapping before safe pushdown.
    if result.get("aliases") or result.get("outputs"):
        return result

    child_columns = _columns(result["child"], schemas)
    if child_columns is None:
        return result

    requested = _resolve_all(
        set(result["columns"]),
        child_columns,
    )
    if requested is None:
        return result

    result["child"] = _push(result["child"], requested, schemas)
    return result
