"""Algorithm semantics tests for E1, E2 and E3."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from pa_vfann.baseline_postfilter import adaptive_postfilter, adaptive_postfilter_from_plan
from pa_vfann.filter_aware import predicate_aware_search
from pa_vfann.fixed_trace import fixed_trace_private_filter
from pa_vfann.graph import Graph
from pa_vfann.search_common import plan_fixed_trace, truncate_outcome


def test_e1_results_are_authorized_and_budget_bounded(small_qdist, small_graph, policy_random):
    outcome = adaptive_postfilter(
        small_qdist[0], small_graph, 20, policy_random.mask, 5, initial_budget=5, query_id=0
    )
    assert outcome.unique_visited_count <= 20
    assert outcome.stop_position == outcome.unique_visited_count
    assert all(v is not None for v in outcome.result_ids if v is not None)
    assert all(bool(policy_random.mask[v]) for v in outcome.result_ids if v is not None)
    assert outcome.legal_candidates_count == sum(bool(policy_random.mask[v]) for v in outcome.visited_nodes)
    assert outcome.policy_dependent


def test_e2_bridge_nodes_never_enter_results(small_qdist, small_graph, policy_clustered):
    outcome = predicate_aware_search(
        small_qdist[1], small_graph, 40, policy_clustered.mask, 5, bridge_r=2,
        initial_budget=40, query_id=1,
    )
    assert all(bool(policy_clustered.mask[v]) for v in outcome.result_ids if v is not None)
    assert outcome.bridge_nodes_count == sum(not bool(policy_clustered.mask[v]) for v in outcome.visited_nodes)
    assert outcome.unique_visited_count <= 40
    assert outcome.bridge_r == 2


def test_e2_bridge_hop_limit_is_enforced_on_a_line_graph():
    n = 5
    adj = tuple(tuple(i + 1 for i in [u] if i + 1 < n) for u in range(n))
    graph = Graph(
        adjacency=adj,
        forward_adjacency=adj,
        degree=1,
        symm=False,
        connected_components=1,
        max_undirected_degree=1,
    )
    qdist = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    mask = np.zeros(n, dtype=bool)
    mask[0] = True
    r1 = predicate_aware_search(qdist, graph, 5, mask, 5, bridge_r=1, initial_budget=5)
    r2 = predicate_aware_search(qdist, graph, 5, mask, 5, bridge_r=2, initial_budget=5)
    assert list(r1.visited_nodes) == [0, 1]
    assert list(r2.visited_nodes) == [0, 1, 2]
    assert r1.returned_count == 1


def test_e3_plan_signature_has_no_policy_parameter():
    params = inspect.signature(plan_fixed_trace).parameters
    forbidden = {"policy", "policy_mask", "authorization", "authorized", "mask", "bits", "legal_count"}
    assert not (set(params) & forbidden)


def test_e3_same_trace_for_different_policies(small_qdist, small_graph, policy_random, policy_clustered):
    budget = 30
    a = fixed_trace_private_filter(small_qdist[2], small_graph, budget, policy_random.mask, 5)
    b = fixed_trace_private_filter(small_qdist[2], small_graph, budget, policy_clustered.mask, 5)
    assert a.visited_nodes == b.visited_nodes
    assert a.stop_position == b.stop_position == budget
    assert not a.policy_dependent and not b.policy_dependent
    assert a.returned_count <= 5 and b.returned_count <= 5


def test_e3_plan_does_not_touch_policy_object(small_qdist, small_graph):
    class ForbiddenMask:
        def __init__(self):
            self.accessed = False

        def __getitem__(self, _):
            self.accessed = True
            raise AssertionError("plan attempted to read authorization bits")

        def __array__(self, *args, **kwargs):
            self.accessed = True
            raise AssertionError("plan attempted to convert authorization bits")

    guard = ForbiddenMask()

    def harmless_filter(visited, row, bits, top_k):
        return [], 0

    outcome = fixed_trace_private_filter(
        small_qdist[3], small_graph, 12, guard, 5, filter_fn=harmless_filter
    )
    assert not guard.accessed
    assert outcome.unique_visited_count == 12
    assert outcome.returned_count == 0
    assert all(v is None for v in outcome.result_ids)


def test_e3_insufficient_results_use_placeholders(small_qdist, small_graph):
    n = small_qdist.shape[1]
    mask = np.zeros(n, dtype=bool)
    mask[int(np.argmin(small_qdist[4]))] = True
    outcome = fixed_trace_private_filter(small_qdist[4], small_graph, 10, mask, 5)
    assert outcome.returned_count == 1
    assert outcome.result_ids.count(None) == 4
    assert outcome.legal_candidates_count == 1


def test_e1_plan_derived_counters_match_direct_search(small_qdist, small_graph, policy_random):
    budget, q, top_k = 50, 9, 5
    full_plan = plan_fixed_trace(small_qdist[q], small_graph, budget)
    derived = adaptive_postfilter_from_plan(
        full_plan[0], full_plan[1], full_plan[2], small_qdist[q], budget,
        policy_random.mask, top_k, initial_budget=5, query_id=q, graph=small_graph,
    )
    direct = adaptive_postfilter(
        small_qdist[q], small_graph, budget, policy_random.mask, top_k,
        initial_budget=5, query_id=q,
    )
    assert derived.visited_nodes == direct.visited_nodes
    assert derived.result_ids == direct.result_ids
    assert derived.expanded_nodes_count == direct.expanded_nodes_count
    assert derived.neighbor_checks_count == direct.neighbor_checks_count


@pytest.mark.parametrize("budget", [20, 40])
def test_budget_prefix_derivation_matches_direct_search(
    small_qdist, small_graph, policy_random, policy_clustered, budget
):
    q = 5
    top_k = 5
    pairs = [
        (
            adaptive_postfilter(small_qdist[q], small_graph, 50, policy_random.mask, top_k, initial_budget=5),
            adaptive_postfilter(small_qdist[q], small_graph, budget, policy_random.mask, top_k, initial_budget=5),
            policy_random.mask,
        ),
        (
            predicate_aware_search(small_qdist[q], small_graph, 50, policy_clustered.mask, top_k, bridge_r=2, initial_budget=5),
            predicate_aware_search(small_qdist[q], small_graph, budget, policy_clustered.mask, top_k, bridge_r=2, initial_budget=5),
            policy_clustered.mask,
        ),
        (
            fixed_trace_private_filter(small_qdist[q], small_graph, 50, policy_random.mask, top_k),
            fixed_trace_private_filter(small_qdist[q], small_graph, budget, policy_random.mask, top_k),
            policy_random.mask,
        ),
    ]
    for full, direct, mask in pairs:
        derived = truncate_outcome(full, budget, small_graph, small_qdist[q], mask, top_k)
        assert derived.visited_nodes == direct.visited_nodes
        assert derived.result_ids == direct.result_ids
        assert derived.expanded_nodes_count == direct.expanded_nodes_count
        assert derived.neighbor_checks_count == direct.neighbor_checks_count
        assert derived.legal_candidates_count == direct.legal_candidates_count


@pytest.mark.parametrize("budget", [0, 1, 20, 10_000])
def test_budget_boundaries(small_qdist, small_graph, policy_random, budget):
    cap = min(max(budget, 0), small_graph.n_nodes)
    e1 = adaptive_postfilter(small_qdist[0], small_graph, budget, policy_random.mask, 5, initial_budget=5)
    e2 = predicate_aware_search(small_qdist[0], small_graph, budget, policy_random.mask, 5, bridge_r=2, initial_budget=5)
    e3 = fixed_trace_private_filter(small_qdist[0], small_graph, budget, policy_random.mask, 5)
    assert 0 <= e1.unique_visited_count <= cap
    assert 0 <= e2.unique_visited_count <= cap
    assert e3.unique_visited_count == cap
    for outcome in (e1, e2, e3):
        assert outcome.expanded_nodes_count >= 0
        assert outcome.neighbor_checks_count >= 0
