"""Krippendorff's Alpha implementation (ordinal) with support for missing
judgments, per https://en.wikipedia.org/wiki/Krippendorff%27s_alpha.

Implemented natively — no external dependency, works with 3+ raters, 1-5
ordinal labels, and missing values (None)."""

from itertools import combinations
from typing import Sequence


def krippendorff_alpha(data: Sequence[Sequence[int | None]], level: str = "ordinal") -> float | None:
    """data: list of units, each a list of rater values (None = missing).
    Returns None when alpha is undefined (e.g., all values equal)."""
    import numpy as np

    units = np.array(data, dtype=object)
    n_raters = units.shape[1]

    values: list[int] = sorted({int(v) for u in units for v in u if v is not None})
    if len(values) < 2:
        return None
    v_index = {v: i for i, v in enumerate(values)}
    n_values = len(values)

    # coincidence matrix n[v][w]
    coincidence = np.zeros((n_values, n_values))
    for unit in units:
        observed = [int(v) for v in unit if v is not None]
        for a, b in combinations(observed, 2):
            coincidence[v_index[a]][v_index[b]] += 1
            coincidence[v_index[b]][v_index[a]] += 1

    m = coincidence.sum()
    if m == 0:
        return None

    def distance(a: int, b: int) -> float:
        if level == "ordinal":
            if a == b:
                return 0.0
            i_a, i_b = v_index[a], v_index[b]
            lo, hi = min(i_a, i_b), max(i_a, i_b)
            return float(sum(values[lo : hi + 1]))
        return float(a != b)

    expected = np.zeros((n_values, n_values))
    row_sums = coincidence.sum(axis=1)
    col_sums = coincidence.sum(axis=0)
    total = m
    for i in range(n_values):
        for j in range(n_values):
            if i != j:
                expected[i][j] = row_sums[i] * col_sums[j] / (total - 1)

    do = sum(coincidence[i][j] * distance(values[i], values[j]) for i in range(n_values) for j in range(n_values))
    de = sum(expected[i][j] * distance(values[i], values[j]) for i in range(n_values) for j in range(n_values))

    if de == 0:
        return None
    return 1.0 - do / de
