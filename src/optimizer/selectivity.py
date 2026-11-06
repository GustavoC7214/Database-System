"""Selectivity estimates for the Module 4 query optimizer."""

from src.optimizer.statistics import ColumnStatistics, StatisticValue

DEFAULT_EQUALITY_SELECTIVITY = 0.1
DEFAULT_RANGE_SELECTIVITY = 1.0 / 3.0
DEFAULT_JOIN_SELECTIVITY = 0.1


def clamp_selectivity(value: float) -> float:
    """Keep a selectivity within the probability interval [0, 1]."""
    return max(0.0, min(1.0, value))


def equality_selectivity(
    column: ColumnStatistics | None,
    value: StatisticValue,
    *,
    n_tuples: int | None = None,
) -> float:
    """Estimate P(column = value).

    Use a matching histogram bucket when available, otherwise 1/NDV.
    For duplicate values spanning multiple buckets, combine their
    estimated frequencies.
    """
    if column is None:
        return DEFAULT_EQUALITY_SELECTIVITY

    if column.ndv == 0:
        return 0.0

    if type(value) is not type(column.minimum):
        return 0.0

    if value < column.minimum or value > column.maximum:
        return 0.0

    if column.histogram:
        total = (
            n_tuples
            if n_tuples is not None
            else sum(bucket.count for bucket in column.histogram)
        )

        if total <= 0:
            return 0.0

        estimated_matches = sum(
            bucket.count / bucket.ndv
            for bucket in column.histogram
            if bucket.lower <= value <= bucket.upper
        )

        if estimated_matches > 0:
            return clamp_selectivity(estimated_matches / total)

    return clamp_selectivity(1.0 / column.ndv)


def range_selectivity(
    column: ColumnStatistics | None,
    operator: str,
    value: StatisticValue,
) -> float:
    """Estimate P(column OP value) for <, <=, >, and >=.

    Numeric histograms use linear interpolation inside each bucket.
    String ranges use an NDV-based fallback because lexicographic
    distances are not meaningful numeric distances.
    """
    if operator not in {"<", "<=", ">", ">="}:
        raise ValueError(f"Unsupported range operator: {operator}")

    if column is None:
        return DEFAULT_RANGE_SELECTIVITY

    if column.ndv == 0:
        return 0.0

    if type(value) is not type(column.minimum):
        return DEFAULT_RANGE_SELECTIVITY

    if isinstance(value, str):
        if operator in {"<", "<="}:
            if value < column.minimum:
                return 0.0
            if value > column.maximum:
                return 1.0
        else:
            if value < column.minimum:
                return 1.0
            if value > column.maximum:
                return 0.0

        return DEFAULT_RANGE_SELECTIVITY

    if not column.histogram:
        minimum = column.minimum
        maximum = column.maximum
        assert isinstance(minimum, int)
        assert isinstance(maximum, int)

        if minimum == maximum:
            if operator == "<":
                return float(minimum < value)
            if operator == "<=":
                return float(minimum <= value)
            if operator == ">":
                return float(minimum > value)
            return float(minimum >= value)

        fraction = clamp_selectivity((value - minimum) / (maximum - minimum))

        if operator in {"<", "<="}:
            return fraction
        return 1.0 - fraction

    total = sum(bucket.count for bucket in column.histogram)
    if total == 0:
        return 0.0

    matches = 0.0

    for bucket in column.histogram:
        lower = bucket.lower
        upper = bucket.upper
        assert isinstance(lower, int)
        assert isinstance(upper, int)

        if lower == upper:
            if operator == "<":
                fraction = float(lower < value)
            elif operator == "<=":
                fraction = float(lower <= value)
            elif operator == ">":
                fraction = float(lower > value)
            else:
                fraction = float(lower >= value)
        else:
            # Treat the integer domain as a continuous interval,
            # with a half-unit correction for inclusive comparisons.
            boundary = value + 0.5 if operator in {"<=", ">"} else value - 0.5

            fraction_below = clamp_selectivity((boundary - lower) / (upper - lower))

            if operator in {"<", "<="}:
                fraction = fraction_below
            else:
                fraction = 1.0 - fraction_below

        matches += bucket.count * fraction

    return clamp_selectivity(matches / total)


def comparison_selectivity(
    column: ColumnStatistics | None,
    operator: str,
    value: StatisticValue,
    *,
    n_tuples: int | None = None,
) -> float:
    """Estimate a column-to-literal comparison."""
    if operator in {"=", "=="}:
        return equality_selectivity(column, value, n_tuples=n_tuples)

    if operator in {"!=", "<>"}:
        return clamp_selectivity(
            1.0 - equality_selectivity(column, value, n_tuples=n_tuples)
        )

    return range_selectivity(column, operator, value)


def and_selectivity(*selectivities: float) -> float:
    """Combine predicates under the independence assumption."""
    result = 1.0
    for selectivity in selectivities:
        result *= clamp_selectivity(selectivity)
    return clamp_selectivity(result)


def or_selectivity(left: float, right: float) -> float:
    """Combine two predicates under the independence assumption."""
    left = clamp_selectivity(left)
    right = clamp_selectivity(right)
    return clamp_selectivity(left + right - left * right)


def not_selectivity(selectivity: float) -> float:
    """Estimate the complement of a predicate."""
    return clamp_selectivity(1.0 - selectivity)


def equijoin_selectivity(
    left: ColumnStatistics | None,
    right: ColumnStatistics | None,
) -> float:
    """Estimate equijoin selectivity using max(NDV_left, NDV_right)."""
    if left is None or right is None:
        return DEFAULT_JOIN_SELECTIVITY

    if left.ndv == 0 or right.ndv == 0:
        return 0.0

    if (
        left.maximum is not None
        and right.minimum is not None
        and type(left.maximum) is type(right.minimum)
        and (left.maximum < right.minimum or right.maximum < left.minimum)
    ):
        return 0.0

    return clamp_selectivity(1.0 / max(left.ndv, right.ndv))
