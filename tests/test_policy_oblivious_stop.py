"""EXP-09 tests for policy-oblivious stopping (T1 fixed count, T2 convergence)."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from pa_vfann.graph import Graph
from pa_vfann.policy_oblivious_stop import (
    T1FixedCountStopper,
    T2DistanceConvergenceStopper,
    run_stop_search,
)
from pa_vfann.search_common import best_first_search, plan_fixed_trace


def _line_graph(n: int) -> Graph:
    adjacency = tuple(
        tuple(v for v in (i - 1, i + 1) if 0 <= v < n) for i in range(n)
    )
    return Graph(
        adjacency=adjacency,
        forward_adjacency=adjacency,
        degree=1,
        symm=True,
        connected_components=1,
        max_undirected_degree=2,
    )


def test_t1_fixed_count_boundaries(small_qdist, small_graph, policy_random):
    row, budget = small_qdist[0], 50
    for fraction, expected in [(0.6, 30), (0.8, 40), (1.0, 50)]:
        stopper = T1FixedCountStopper(budget, fraction)
        outcome, decision, _ = run_stop_search(
            f"T1_{fraction}", row, small_graph, budget, policy_random.mask, 5, stopper
        )
        assert decision.stop_reason == "fixed_count"
        assert decision.stop_position == expected
        assert outcome.unique_visited_count == expected
        assert outcome.stop_position == expected
        assert not outcome.policy_dependent

    with pytest.raises(ValueError):
        T1FixedCountStopper(50, 0.0)
    with pytest.raises(ValueError):
        T1FixedCountStopper(50, 1.01)


def _corridor_graph(n: int) -> Graph:
    adjacency = tuple(
        tuple(v for v in (i - 1, i + 1) if 0 <= v < n) for i in range(n)
    )
    return Graph(
        adjacency=adjacency,
        forward_adjacency=adjacency,
        degree=1,
        symm=True,
        connected_components=1,
        max_undirected_degree=2,
    )


def _corridor_distances(n: int = 80) -> np.ndarray:
    """Seed at 0; near nodes sit behind a far corridor 1..20."""
    row = np.zeros(n, dtype=np.float64)
    row[0] = 0.0
    row[1:21] = 100 + np.arange(20)
    row[21:] = np.arange(1, n - 20)
    return row


def test_t2_does_not_stop_before_minimum_visits(small_qdist, small_graph):
    """No convergence check is evaluated before min_fraction * B visits."""
    row, budget = _corridor_distances(), 50
    stopper = T2DistanceConvergenceStopper(
        row, budget, k=10, min_fraction=0.6, m=8, epsilon=0.001
    )
    visited, _, _ = best_first_search(row, _corridor_graph(len(row)), budget, stop_when=stopper)
    decision = stopper.decision(len(visited))
    assert decision.checks_evaluated > 0
    assert min(t for t, _ in decision.delta_trace) >= 30   # 0.6 * 50
    assert decision.stop_position >= 30


def test_t2_convergence_on_constant_d10_line_graph():
    """Once 10 nodes are visited on a monotone line, d10 stops improving."""
    n = 80
    graph = _line_graph(n)
    row = np.arange(n, dtype=np.float32) ** 2  # strictly increasing distances
    budget = 50
    stopper = T2DistanceConvergenceStopper(
        row, budget=budget, k=10, min_fraction=0.6, m=8, epsilon=0.001
    )
    visited, _, _ = best_first_search(row, graph, budget, stop_when=stopper)
    decision = stopper.decision(len(visited))
    assert decision.stop_reason == "distance_converged"
    assert decision.stop_position >= 30               # min_fraction * B = 30
    assert decision.stop_position < budget            # actually stopped early
    assert len(decision.delta_trace) >= 8
    assert all(d <= 0.001 for _, d in decision.delta_trace[-8:])


def test_t2_reaches_max_budget_without_convergence():
    row = _corridor_distances()
    graph = _corridor_graph(len(row))
    budget = 50
    # m=16: the corridor keeps d10 improving past the last available check.
    stopper = T2DistanceConvergenceStopper(
        row, budget, k=10, min_fraction=0.6, m=16, epsilon=0.001
    )
    visited, _, _ = best_first_search(row, graph, budget, stop_when=stopper)
    decision = stopper.decision(len(visited))
    assert decision.stop_reason == "max_budget"
    assert decision.stop_position == budget
    assert any(d > 0.001 for _, d in decision.delta_trace[:-8])


def test_t2_predicate_has_no_policy_parameter():
    init_params = set(inspect.signature(T2DistanceConvergenceStopper.__init__).parameters)
    call_params = set(inspect.signature(T2DistanceConvergenceStopper.__call__).parameters)
    for forbidden in ("policy", "mask", "authorization", "authorization_bits", "filter_result"):
        assert forbidden not in init_params
        assert forbidden not in call_params
    assert call_params == {"self", "visited"}


def test_stop_trace_invariant_across_policies(small_qdist, small_graph, policy_random, policy_clustered):
    row, budget = small_qdist[0], 50
    for label, make in [
        ("T1", lambda: T1FixedCountStopper(budget, 0.6)),
        ("T2", lambda: T2DistanceConvergenceStopper(
            row, budget, k=5, min_fraction=0.6, m=8, epsilon=0.001
        )),
    ]:
        out_a, dec_a, _ = run_stop_search(
            label, row, small_graph, budget, policy_random.mask, 5, make()
        )
        out_b, dec_b, _ = run_stop_search(
            label, row, small_graph, budget, policy_clustered.mask, 5, make()
        )
        assert out_a.visited_nodes == out_b.visited_nodes
        assert dec_a.stop_position == dec_b.stop_position
        assert dec_a.stop_reason == dec_b.stop_reason
        assert out_a.neighbor_checks_count == out_b.neighbor_checks_count


def test_stopped_trace_is_exact_prefix_of_e3_plan(small_qdist, small_graph, policy_random):
    row, budget = small_qdist[1], 50
    full_plan = plan_fixed_trace(row, small_graph, budget)[0]
    stopper = T1FixedCountStopper(budget, 0.6)
    outcome, _, _ = run_stop_search(
        "T1_prefix", row, small_graph, budget, policy_random.mask, 5, stopper
    )
    assert tuple(outcome.visited_nodes) == full_plan[:30]


def test_e3_original_implementation_unchanged(small_qdist, small_graph, policy_random):
    """E3 still visits the full budget; EXP-09 never touched fixed_trace.py."""
    from pa_vfann.fixed_trace import fixed_trace_private_filter

    outcome = fixed_trace_private_filter(small_qdist[0], small_graph, 50, policy_random.mask, 5)
    assert outcome.unique_visited_count == 50
    assert outcome.algorithm == "E3_FIXED_TRACE"
