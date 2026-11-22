"""Lazy-distance search state machine with four separate cost counters.

EXP-02 model (no global distance oracle):
  * There is no query-to-all-vectors distance table anywhere in search.
  * A distance is computed the first time a node is discovered (enters the
    candidate queue) and cached for that query; repeated lookups are free.
  * The public entry node is a fixed config constant, never argmin(row).
  * Budget counts NODE EXPANSIONS: one expansion consumes one unit.
  * Discovered / visited / expanded / neighbour-check counts are never mixed.

Visits may exceed expansions by one: after the last permitted expansion the
best queued node is still popped and recorded, but it is never expanded. This
is explicit and identical for E1/E2/E3.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .transfer import candidate_transfer_bytes

@dataclass(frozen=True)
class Snapshot:
    """Cumulative counters immediately after each visited node."""

    expanded: int
    neighbor_checks: int
    distance_evaluations: int
    n_discovered: int
    n_visited: int


@dataclass(frozen=True)
class SearchLog:
    algorithm: str
    query_id: int
    entry_node: int
    bridge_r: int | None
    discovery_sequence: tuple[int, ...]
    visit_sequence: tuple[int, ...]
    expansion_sequence: tuple[int, ...]
    snapshots: tuple[Snapshot, ...]
    distances: dict[int, float]
    termination_reason: str
    early_stop_index: int | None


@dataclass(frozen=True)
class SearchOutcome:
    algorithm: str
    query_id: int
    budget: int
    bridge_r: int | None
    entry_node: int
    discovery_sequence: tuple[int, ...]
    visit_sequence: tuple[int, ...]
    expansion_sequence: tuple[int, ...]
    distance_evaluations: int
    unique_discovered_nodes: int
    unique_visited_nodes: int
    expanded_nodes: int
    neighbor_checks: int
    candidate_count: int
    candidate_id_bytes: int
    candidate_meta_bytes: int
    candidate_vector_bytes: int
    candidate_transfer_bytes: int
    legal_candidates_count: int
    result_ids: tuple[int | None, ...]
    returned_count: int
    stop_position: int
    termination_reason: str
    policy_dependent: bool
    note: str = ""

    @property
    def trace_sha(self) -> str:
        import hashlib

        raw = ",".join(str(v) for v in self.visit_sequence).encode("ascii")
        return hashlib.sha256(raw).hexdigest()[:16]


class DistanceMeter:
    """Per-query lazy squared-L2 cache; counts only actual computations."""

    def __init__(self, query: np.ndarray, vectors: np.ndarray):
        self.query = np.asarray(query, dtype=np.float32)
        self.vectors = np.asarray(vectors, dtype=np.float32)
        self.cache: dict[int, float] = {}
        self.evaluations = 0

    def get(self, node_id: int) -> float:
        node = int(node_id)
        if node not in self.cache:
            diff = self.vectors[node] - self.query
            self.cache[node] = float(np.dot(diff, diff))
            self.evaluations += 1
        return self.cache[node]


def _bits(policy_mask: np.ndarray | None) -> np.ndarray | None:
    return None if policy_mask is None else np.asarray(policy_mask, dtype=bool)


def traverse(
    query: np.ndarray,
    vectors: np.ndarray,
    graph,
    entry_node: int,
    max_expansions: int,
    *,
    mode: str,
    policy_mask: np.ndarray | None = None,
    bridge_r: int | None = None,
    top_k: int = 10,
    min_expansions: int = 20,
) -> SearchLog:
    """Run one best-first search at the maximum expansion budget.

    ``mode`` is E1, E2 or E3. E3 is called with ``policy_mask=None`` and its
    code path never indexes any authorization bit. E2 requires ``bridge_r>=1``.
    """
    if mode not in ("E1", "E2", "E3"):
        raise ValueError(f"unknown search mode: {mode}")
    if mode == "E3" and policy_mask is not None:
        raise ValueError("E3 search must not receive a policy mask")
    if mode in ("E1", "E2") and policy_mask is None:
        raise ValueError(f"{mode} requires a policy mask")
    if mode == "E2" and (bridge_r is None or int(bridge_r) < 1):
        raise ValueError("E2 requires bridge_r >= 1")

    entry = int(entry_node)
    max_expansions = max(int(max_expansions), 0)
    empty = SearchLog(
        algorithm=mode, query_id=0, entry_node=entry, bridge_r=bridge_r,
        discovery_sequence=(), visit_sequence=(), expansion_sequence=(),
        snapshots=(), distances={}, termination_reason="expansion_budget",
        early_stop_index=None,
    )
    if max_expansions == 0:
        return empty

    mask = _bits(policy_mask)
    meter = DistanceMeter(query, vectors)
    discovered: set[int] = set()
    hops: dict[int, int] = {}
    discovery: list[int] = []
    visits: list[int] = []
    expansions: list[int] = []
    snapshots: list[Snapshot] = []
    heap: list[tuple[float, int]] = []
    legal_discovered = 0
    expanded = 0
    neighbor_checks = 0
    early_stop_index: int | None = None
    termination = "queue_exhausted"

    def discover(node: int, hop: int) -> None:
        nonlocal legal_discovered
        node = int(node)
        if node in discovered:
            return
        discovered.add(node)
        hops[node] = int(hop)
        distance = meter.get(node)  # the ONLY distance computation site
        discovery.append(node)
        heapq.heappush(heap, (distance, node))
        if mask is not None and bool(mask[node]):
            legal_discovered += 1

    discover(entry, 0)

    while heap:
        _, node = heapq.heappop(heap)
        node = int(node)
        visits.append(node)
        # Snapshot is taken BEFORE this node is expanded: counters describe the
        # state seen when the node is popped, which is what a smaller budget
        # would also see at the same visit position.
        snapshots.append(Snapshot(expanded, neighbor_checks, meter.evaluations,
                                  len(discovery), len(visits)))

        if mode == "E1" and expanded >= int(min_expansions) and legal_discovered >= int(top_k):
            termination = "early_stop"
            early_stop_index = len(visits) - 1
            break

        if expanded >= max_expansions:
            termination = "expansion_budget"
            break

        expansions.append(node)
        expanded += 1
        authorized = bool(mask[node]) if mask is not None else False
        hop = hops[node]

        for nxt in graph.adjacency[node]:
            neighbor_checks += 1
            nxt = int(nxt)
            if nxt in discovered:
                continue
            if mode == "E2":
                if bool(mask[nxt]):
                    discover(nxt, 0)               # authorized neighbour: reset chain
                elif authorized:
                    discover(nxt, 1)               # bridge after an authorized node
                elif hop < int(bridge_r):
                    discover(nxt, hop + 1)         # extend bridge chain within r
                # else: unauthorized neighbour beyond r is checked but not discovered
            else:
                discover(nxt, 0)                   # E1/E3: distance-only discovery

    # If the queue empties right after the final expansion there is no further
    # visit to carry that expansion's counters. Append a terminal snapshot so
    # deriving at the maximum budget still reports the full cost.
    if snapshots and (
        snapshots[-1].expanded != expanded
        or snapshots[-1].n_discovered != len(discovery)
    ):
        snapshots.append(Snapshot(expanded, neighbor_checks, meter.evaluations,
                                  len(discovery), len(visits)))

    return SearchLog(
        algorithm=mode,
        query_id=0,
        entry_node=entry,
        bridge_r=int(bridge_r) if bridge_r is not None else None,
        discovery_sequence=tuple(discovery),
        visit_sequence=tuple(visits),
        expansion_sequence=tuple(expansions),
        snapshots=tuple(snapshots),
        distances=dict(meter.cache),
        termination_reason=termination,
        early_stop_index=early_stop_index,
    )


def derive_outcome(
    log: SearchLog,
    budget: int,
    policy_mask: np.ndarray | None,
    top_k: int,
    dimension: int,
    *,
    query_id: int = 0,
    note: str = "",
) -> SearchOutcome:
    """Derive the exact outcome for an expansion budget from a max-budget log.

    All decisions (priority, enqueue, bridge hop, stopping) depend only on the
    prefix already recorded, so a smaller-budget run is an exact prefix. Cost
    counters are taken from the recorded snapshot, never scaled or inferred
    from another metric.
    """
    budget = max(int(budget), 0)
    algorithm = {"E1": "E1_POSTFILTER", "E2": "E2_BRIDGE", "E3": "E3_FIXED_TRACE"}[log.algorithm]
    if budget == 0 or not log.snapshots:
        return SearchOutcome(
            algorithm=algorithm, query_id=query_id, budget=budget, bridge_r=log.bridge_r,
            entry_node=log.entry_node, discovery_sequence=(), visit_sequence=(),
            expansion_sequence=(), distance_evaluations=0, unique_discovered_nodes=0,
            unique_visited_nodes=0, expanded_nodes=0, neighbor_checks=0,
            candidate_count=0, **candidate_transfer_bytes(0, dimension),
            legal_candidates_count=0, result_ids=(None,) * int(top_k), returned_count=0,
            stop_position=0, termination_reason="expansion_budget",
            policy_dependent=log.algorithm != "E3", note=note,
        )

    # With budget B the search performs B expansions, then pops one final node
    # which is visited but not expanded. The max-budget log stores a snapshot
    # after every visit, so the matching prefix ends at the LAST snapshot whose
    # expanded count is still B (equivalently: just before the first snapshot
    # with expanded > B).
    idx = next(
        (i - 1 for i, snap in enumerate(log.snapshots) if snap.expanded > budget),
        len(log.snapshots) - 1,
    )
    snap = log.snapshots[idx]
    discovery = log.discovery_sequence[: snap.n_discovered]
    visits = log.visit_sequence[: snap.n_visited]
    expansions = log.expansion_sequence[: snap.expanded]

    if log.early_stop_index is not None and log.early_stop_index <= idx:
        termination = "early_stop"
    elif snap.expanded >= budget:
        termination = "expansion_budget"
    else:
        termination = log.termination_reason

    # Candidate filtering happens after the search (E1/E2 server-side match
    # bit, E3 simulated client-side secret filter). It never changes the trace.
    mask = _bits(policy_mask)
    if mask is None:
        legal: list[int] = []
    else:
        legal = [int(v) for v in discovery if bool(mask[int(v)])]
    ranked = sorted(legal, key=lambda v: (log.distances[v], v))[: int(top_k)]
    result_ids: list[int | None] = list(ranked)
    result_ids.extend([None] * (int(top_k) - len(result_ids)))

    return SearchOutcome(
        algorithm=algorithm,
        query_id=query_id,
        budget=budget,
        bridge_r=log.bridge_r,
        entry_node=log.entry_node,
        discovery_sequence=discovery,
        visit_sequence=visits,
        expansion_sequence=expansions,
        distance_evaluations=snap.distance_evaluations,
        unique_discovered_nodes=snap.n_discovered,
        unique_visited_nodes=snap.n_visited,
        expanded_nodes=snap.expanded,
        neighbor_checks=snap.neighbor_checks,
        candidate_count=snap.n_discovered,
        **candidate_transfer_bytes(snap.n_discovered, dimension),
        legal_candidates_count=len(legal),
        result_ids=tuple(result_ids),
        returned_count=len(ranked),
        stop_position=len(visits),
        termination_reason=termination,
        policy_dependent=log.algorithm != "E3",
        note=note,
    )
