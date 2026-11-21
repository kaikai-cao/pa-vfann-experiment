"""E1: Adaptive Post-filter (policy-aware early stopping).

The traversal priority is distance-only, identical to E3. The sole adaptive
component is the stopping rule: once the policy-aware service observes at
least K authorized records among the visited nodes (and at least
``initial_budget`` visits have occurred), it stops early. All authorization
checks are post-hoc over the visited set; no unauthorized node is boosted or
suppressed in the priority queue.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .graph import Graph
from .search_common import SearchOutcome, assemble_outcome, best_first_search


def adaptive_postfilter_from_plan(
    visited: Sequence[int],
    expanded: int,
    neighbor_checks: int,
    query_distances_row: np.ndarray,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    initial_budget: int = 20,
    query_id: int = 0,
    graph: Graph | None = None,
) -> SearchOutcome:
    """Apply the E1 stopping rule to an already computed public traversal.

    Used by the batch runner so the E1/E3 plan is computed only once per
    (query, budget). The stopping rule is the only policy-dependent step.
    Expansion/neighbour-check counters MUST be recomputed for the kept prefix;
    otherwise they would describe the unstopped full-budget traversal.
    """
    bits = np.asarray(policy_mask, dtype=bool)
    legal_seen = 0
    min_visits = min(int(initial_budget), max(int(budget), 0))
    stop = len(visited)
    for position, node in enumerate(visited, start=1):
        if bits[int(node)]:
            legal_seen += 1
        if position >= min_visits and legal_seen >= top_k:
            stop = position
            break
    kept = tuple(visited[:stop])
    legal_ids = [int(v) for v in kept if bits[int(v)]]
    if graph is not None:
        expanded = max(len(kept) - 1, 0)
        neighbor_checks = sum(len(graph.adjacency[int(v)]) for v in kept[:-1])
    return assemble_outcome(
        algorithm="E1_POSTFILTER",
        query_id=query_id,
        budget=budget,
        bridge_r=None,
        visited=kept,
        expanded=expanded,
        neighbor_checks=neighbor_checks,
        legal_ids=legal_ids,
        query_distances_row=query_distances_row,
        top_k=top_k,
        policy_dependent=True,
        note="distance-only traversal; policy-aware early stop (plan shared with E3)",
    )


def adaptive_postfilter(
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    initial_budget: int = 20,
    query_id: int = 0,
) -> SearchOutcome:
    row = np.asarray(query_distances_row)
    bits = np.asarray(policy_mask, dtype=bool)
    legal_count = 0
    min_visits = min(int(initial_budget), max(int(budget), 0))

    def stop_when(visited) -> bool:
        nonlocal legal_count
        if bits[int(visited[-1])]:
            legal_count += 1
        return len(visited) >= min_visits and legal_count >= top_k

    visited, expanded, checks = best_first_search(row, graph, budget, stop_when)
    legal_ids = [int(v) for v in visited if bits[int(v)]]
    return assemble_outcome(
        algorithm="E1_POSTFILTER",
        query_id=query_id,
        budget=budget,
        bridge_r=None,
        visited=visited,
        expanded=expanded,
        neighbor_checks=checks,
        legal_ids=legal_ids,
        query_distances_row=row,
        top_k=top_k,
        policy_dependent=True,
        note="distance-only traversal; policy-aware early stop",
    )
