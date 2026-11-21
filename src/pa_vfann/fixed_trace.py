"""E3: Fixed-trace Private Filtering (focus of EXP-01).

Steps:
  1. Build a search plan from (query, public graph, budget) only.
  2. Visit exactly that plan; never stop early on legal-result counts.
  3. Apply the simulated secret filter after traversal.
  4. Emit placeholders when fewer than K legal records were found.

Invariant under test: for fixed q, G and B, changing the authorization policy
does not change the visited-node sequence.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .graph import Graph
from .search_common import SearchOutcome, assemble_outcome, plan_fixed_trace
from .secret_filter import simulated_secret_filter


def fixed_trace_from_plan(
    plan: tuple[Sequence[int], int, int],
    query_distances_row: np.ndarray,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    query_id: int = 0,
    filter_fn=simulated_secret_filter,
) -> SearchOutcome:
    """Apply E3's simulated filter to an already computed public plan."""
    visited, expanded, checks = plan
    legal_topk, legal_total = filter_fn(visited, query_distances_row, policy_mask, top_k)
    return assemble_outcome(
        algorithm="E3_FIXED_TRACE",
        query_id=query_id,
        budget=budget,
        bridge_r=None,
        visited=tuple(visited),
        expanded=expanded,
        neighbor_checks=checks,
        legal_ids=legal_topk,
        query_distances_row=query_distances_row,
        top_k=top_k,
        policy_dependent=False,
        legal_candidates_count=legal_total,
        note="plan independent of policy; simulated secret filter after full trace",
    )


def fixed_trace_private_filter(
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    query_id: int = 0,
    filter_fn=simulated_secret_filter,
) -> SearchOutcome:
    # The plan is computed before and independently of any authorization bit.
    visited, expanded, checks = plan_fixed_trace(query_distances_row, graph, budget)
    legal_topk, legal_total = filter_fn(visited, query_distances_row, policy_mask, top_k)
    return assemble_outcome(
        algorithm="E3_FIXED_TRACE",
        query_id=query_id,
        budget=budget,
        bridge_r=None,
        visited=visited,
        expanded=expanded,
        neighbor_checks=checks,
        legal_ids=legal_topk,
        legal_candidates_count=legal_total,
        query_distances_row=query_distances_row,
        top_k=top_k,
        policy_dependent=False,
        note="plan independent of policy; simulated secret filter after full trace",
    )
