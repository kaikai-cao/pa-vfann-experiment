"""Shared best-first traversal, budget accounting and result assembly.

Budget semantics (identical for E1, E2 and E3):
  * ``budget`` caps the number of UNIQUE visited nodes (first-visit order).
  * ``expanded_nodes_count`` counts nodes whose neighbour list was enumerated.
  * ``neighbor_checks_count`` counts individual directed neighbour inspections,
    including repeats. These three numbers are never mixed into one metric.

All algorithms use squared L2 distances from the precomputed query-distance
table and break ties by ascending node id. The graph is fixed and public.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from .graph import Graph


@dataclass(frozen=True)
class SearchOutcome:
    algorithm: str
    query_id: int
    budget: int
    bridge_r: int | None
    visited_nodes: tuple[int, ...]
    expanded_nodes_count: int
    neighbor_checks_count: int
    stop_position: int
    legal_candidates_count: int
    result_ids: tuple[int | None, ...]
    result_distances: tuple[float | None, ...]
    returned_count: int
    policy_dependent: bool
    bridge_nodes_count: int = 0
    note: str = ""

    @property
    def unique_visited_count(self) -> int:
        return len(self.visited_nodes)


def best_first_search(
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
    stop_when: Callable[[Sequence[int]], bool] | None = None,
) -> tuple[tuple[int, ...], int, int]:
    """Best-first graph traversal over unique visited nodes.

    ``stop_when`` is evaluated after each visit and may read policy bits only
    when the caller explicitly supplies such a predicate (E1). E3 calls this
    with ``stop_when=None`` and never consults authorization state.
    """
    budget = max(int(budget), 0)
    if budget == 0:
        return (), 0, 0
    row = np.asarray(query_distances_row)
    seed = int(np.argmin(row))  # exact nearest graph node, tie broken by index
    heap: list[tuple[float, int]] = [(float(row[seed]), seed)]
    visited: list[int] = []
    seen: set[int] = set()
    expanded = 0
    neighbor_checks = 0
    while heap and len(visited) < budget:
        _, node = heapq.heappop(heap)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        if stop_when is not None and stop_when(visited):
            break
        if len(visited) >= budget:
            break
        expanded += 1
        for nxt in graph.adjacency[node]:
            neighbor_checks += 1
            if nxt not in seen:
                heapq.heappush(heap, (float(row[nxt]), int(nxt)))
    return tuple(visited), expanded, neighbor_checks


def plan_fixed_trace(
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
) -> tuple[tuple[int, ...], int, int]:
    """Public search plan: depends only on (query, graph, budget).

    No policy, authorization label, match bit or legal-result count is
    available to this function. This is the E3 trace-invariance property.
    """
    return best_first_search(query_distances_row, graph, budget, stop_when=None)


def truncate_outcome(
    outcome: SearchOutcome,
    budget: int,
    graph: Graph,
    query_distances_row: np.ndarray,
    policy_mask: np.ndarray,
    top_k: int,
) -> SearchOutcome:
    """Derive the outcome for a smaller budget from a max-budget run.

    Budget only caps traversal length; it does not alter priority, enqueue or
    stopping rules (initial_budget is 20 and all reported budgets are >= 20).
    Therefore every smaller-budget search is an exact prefix of the max-budget
    search. Cost counters are recomputed from the prefix, not scaled.
    """
    budget = max(int(budget), 0)
    kept = tuple(outcome.visited_nodes[:budget])
    if len(kept) == len(outcome.visited_nodes):
        return SearchOutcome(
            **{**outcome.__dict__, "budget": budget}
        )
    expanded = max(len(kept) - 1, 0)
    checks = sum(len(graph.adjacency[int(v)]) for v in kept[:-1])
    bits = np.asarray(policy_mask, dtype=bool)
    legal_ids = [int(v) for v in kept if bits[int(v)]]
    bridge_count = sum(1 for v in kept if not bits[int(v)]) if outcome.algorithm.startswith("E2") else outcome.bridge_nodes_count
    return assemble_outcome(
        algorithm=outcome.algorithm,
        query_id=outcome.query_id,
        budget=budget,
        bridge_r=outcome.bridge_r,
        visited=kept,
        expanded=expanded,
        neighbor_checks=checks,
        legal_ids=legal_ids,
        query_distances_row=query_distances_row,
        top_k=top_k,
        policy_dependent=outcome.policy_dependent,
        bridge_nodes_count=bridge_count,
        note=outcome.note + "; derived as exact budget prefix",
    )


def assemble_outcome(
    algorithm: str,
    query_id: int,
    budget: int,
    bridge_r: int | None,
    visited: tuple[int, ...],
    expanded: int,
    neighbor_checks: int,
    legal_ids: Sequence[int],
    query_distances_row: np.ndarray,
    top_k: int,
    policy_dependent: bool,
    legal_candidates_count: int | None = None,
    bridge_nodes_count: int = 0,
    note: str = "",
) -> SearchOutcome:
    row = np.asarray(query_distances_row)
    ranked = sorted((int(v) for v in legal_ids), key=lambda v: (float(row[v]), v))[:top_k]
    result_ids: list[int | None] = list(ranked)
    result_distances: list[float | None] = [float(row[v]) for v in ranked]
    while len(result_ids) < top_k:
        result_ids.append(None)
        result_distances.append(None)
    return SearchOutcome(
        algorithm=algorithm,
        query_id=int(query_id),
        budget=int(budget),
        bridge_r=int(bridge_r) if bridge_r is not None else None,
        visited_nodes=tuple(visited),
        expanded_nodes_count=int(expanded),
        neighbor_checks_count=int(neighbor_checks),
        stop_position=len(visited),
        legal_candidates_count=int(legal_candidates_count) if legal_candidates_count is not None else len(legal_ids),
        result_ids=tuple(result_ids),
        result_distances=tuple(result_distances),
        returned_count=len(ranked),
        policy_dependent=bool(policy_dependent),
        bridge_nodes_count=int(bridge_nodes_count),
        note=note,
    )
