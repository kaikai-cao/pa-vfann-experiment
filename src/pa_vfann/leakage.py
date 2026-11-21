"""Trace-level leakage measurements (search trace only, not cryptographic privacy).

Four channels are reported separately:
  * search trace / visited set and order;
  * stopping position;
  * returned result count;
  * returned record ids.

E3 only removes policy dependence from the *search plan*. Output information
and the fact that the graph itself is public are not hidden by this property.
"""

from __future__ import annotations

from collections.abc import Sequence


def set_leakage(trace_a: Sequence[int], trace_b: Sequence[int]) -> float:
    """1 - Jaccard similarity; two empty sets give 0 by convention."""
    a, b = set(trace_a), set(trace_b)
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)


def normalized_edit_distance(seq_a: Sequence[int], seq_b: Sequence[int]) -> float:
    """Levenshtein distance / max length, with common prefix/suffix trimmed."""
    a, b = list(seq_a), list(seq_b)
    if a == b:
        return 0.0
    if not a or not b:
        return 1.0
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < min(len(a), len(b)) - prefix
        and a[len(a) - 1 - suffix] == b[len(b) - 1 - suffix]
    ):
        suffix += 1
    a_mid = a[prefix : len(a) - suffix]
    b_mid = b[prefix : len(b) - suffix]
    denominator = max(len(a), len(b))
    if not a_mid or not b_mid:
        return abs(len(a_mid) - len(b_mid)) / denominator
    previous = list(range(len(b_mid) + 1))
    for i, ca in enumerate(a_mid, start=1):
        current = [i]
        for j, cb in enumerate(b_mid, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / denominator


def trace_leakage(
    trace_a: Sequence[int],
    trace_b: Sequence[int],
    stop_a: int,
    stop_b: int,
    returned_a: Sequence[int | None],
    returned_b: Sequence[int | None],
) -> dict[str, float | int]:
    """Compute four independently reported leakage channels."""
    set_a, set_b = set(trace_a), set(trace_b)
    ids_a = set(int(v) for v in returned_a if v is not None)
    ids_b = set(int(v) for v in returned_b if v is not None)
    return {
        "L_set": set_leakage(trace_a, trace_b),
        "L_seq": normalized_edit_distance(trace_a, trace_b),
        "stop_position_delta": abs(int(stop_a) - int(stop_b)),
        "returned_count_delta": abs(len(ids_a) - len(ids_b)),
        "L_output_ids": set_leakage(ids_a, ids_b),
        "intersection_size": len(set_a & set_b),
        "union_size": len(set_a | set_b),
    }
