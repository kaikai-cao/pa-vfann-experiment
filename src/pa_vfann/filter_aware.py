"""E2: Predicate-aware Search -- an explicit, reproducible controlled bridge.

Rules (all fixed here, no hidden heuristics):
  1. Only authorized nodes enter the result candidate set.
  2. Unauthorized nodes may be visited and expanded as bridge nodes but can
     never be returned.
  3. A bridge chain may contain at most ``r`` consecutive unauthorized nodes
     since the last authorized node; authorized neighbours are always
     enqueueable and reset the chain counter.
  4. Duplicate enqueues are resolved lazily: the first heap pop fixes a node's
     bridge-hop count; later entries are discarded.
  5. Priority is (squared L2 distance to query, hop, node id).
  6. Budget is the number of unique visited nodes, counting bridge nodes too.

This is a custom experimental baseline. It is NOT ACORN or RACORN.
"""

from __future__ import annotations

import heapq

import numpy as np

from .graph import Graph
from .search_common import SearchOutcome, assemble_outcome


def predicate_aware_search(
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    bridge_r: int,
    initial_budget: int = 20,
    query_id: int = 0,
) -> SearchOutcome:
    if int(bridge_r) < 1:
        raise ValueError("bridge_r must be >= 1")
    row = np.asarray(query_distances_row)
    bits = np.asarray(policy_mask, dtype=bool)
    budget = max(int(budget), 0)
    if budget == 0:
        return assemble_outcome(
            "E2_BRIDGE", query_id, budget, bridge_r, (), 0, 0, (), row, top_k, True,
            note="empty budget",
        )

    seed = int(np.argmin(row))
    heap: list[tuple[float, int, int]] = [(float(row[seed]), 0, seed)]
    visited: list[int] = []
    seen: set[int] = set()
    legal: list[int] = []
    expanded = 0
    neighbor_checks = 0
    min_visits = min(int(initial_budget), budget)

    while heap and len(visited) < budget:
        _, hop, node = heapq.heappop(heap)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        if bits[node]:
            legal.append(node)
            next_hop = 0
        else:
            next_hop = hop
        if len(visited) >= min_visits and len(legal) >= top_k:
            break
        if len(visited) >= budget:
            break
        expanded += 1
        for nxt in graph.adjacency[node]:
            neighbor_checks += 1
            if nxt in seen:
                continue
            if bits[int(nxt)]:
                heapq.heappush(heap, (float(row[nxt]), 0, int(nxt)))
            elif next_hop + 1 <= bridge_r:
                heapq.heappush(heap, (float(row[nxt]), next_hop + 1, int(nxt)))

    bridge_count = sum(1 for node in visited if not bits[int(node)])
    return assemble_outcome(
        algorithm="E2_BRIDGE",
        query_id=query_id,
        budget=budget,
        bridge_r=bridge_r,
        visited=tuple(visited),
        expanded=expanded,
        neighbor_checks=neighbor_checks,
        legal_ids=legal,
        query_distances_row=row,
        top_k=top_k,
        policy_dependent=True,
        bridge_nodes_count=bridge_count,
        note=f"controlled bridge r={bridge_r}; unauthorized nodes never in results",
    )
