"""Tests 7-12, 14: E1 stop rule, E2 bridge, E3 invariance, budgets, bytes."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import PoisonMask, tiny_config
from pa_vfann_exp02.algorithms import derive, run_log, run_search
from pa_vfann_exp02.lazy_search import traverse
from pa_vfann_exp02.transfer import candidate_transfer_bytes


def test_7_e1_early_stop_is_policy_driven_and_legal(config, small_env, masks):
    _, dataset, graph = small_env
    policy = masks["random_high"]
    log = run_log(dataset.query_vectors[0], dataset.vectors, graph, config,
                  "E1_POSTFILTER", policy_mask=policy.mask, max_expansions=200)
    assert log.early_stop_index is not None
    outcome = derive(log, config, 200, policy_mask=policy.mask)
    assert outcome.termination_reason == "early_stop"
    assert outcome.expanded_nodes <= 200
    assert outcome.legal_candidates_count >= config["search"]["top_k"]
    assert all(v is None or policy.mask[int(v)] for v in outcome.result_ids)


def test_8_e2_bridge_nodes_never_enter_results(config, small_env, masks):
    _, dataset, graph = small_env
    policy = masks["random_low"]
    for r in config["search"]["bridge_r_values"]:
        outcome = run_search(dataset.query_vectors[0], dataset.vectors, graph, config,
                             "E2_BRIDGE", 200, policy_mask=policy.mask, bridge_r=int(r))
        assert all(v is None or policy.mask[int(v)] for v in outcome.result_ids)
        assert outcome.termination_reason in ("expansion_budget", "queue_exhausted")
        assert outcome.expanded_nodes == len(outcome.expansion_sequence)
        assert outcome.distance_evaluations == outcome.unique_discovered_nodes


def test_9_e2_bridge_cap_is_exact():
    config = tiny_config(n=4, dim=2, entry=0)
    vectors = np.asarray([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [9.0, 0.0]], dtype=np.float32)

    class Chain:
        adjacency = ((1,), (2,), (3,), ())

    mask = np.asarray([False, False, False, True])
    r1 = traverse(vectors[0], vectors, Chain(), 0, 4, mode="E2", policy_mask=mask, bridge_r=1)
    assert 3 not in r1.discovery_sequence
    r2 = traverse(vectors[0], vectors, Chain(), 0, 4, mode="E2", policy_mask=mask, bridge_r=2)
    assert 3 in r2.discovery_sequence
    assert len(r2.expansion_sequence) <= 4


def test_10_e3_never_receives_policy_and_is_trace_invariant(config, small_env, masks):
    _, dataset, graph = small_env
    with pytest.raises(ValueError):
        traverse(dataset.query_vectors[0], dataset.vectors, graph, 881, 100,
                 mode="E3", policy_mask=PoisonMask())
    results = []
    for policy in masks.values():
        outcome = run_search(dataset.query_vectors[0], dataset.vectors, graph, config,
                             "E3_FIXED_TRACE", 200, policy_mask=policy.mask)
        results.append(outcome)
        assert not outcome.policy_dependent
    assert results[0].discovery_sequence == results[1].discovery_sequence == results[2].discovery_sequence
    assert results[0].visit_sequence == results[1].visit_sequence == results[2].visit_sequence
    assert results[0].expansion_sequence == results[1].expansion_sequence == results[2].expansion_sequence
    assert len({o.legal_candidates_count for o in results}) > 1


@pytest.mark.parametrize("budget", [0, 1, 20, 200])
def test_11_budget_boundaries_and_prefixed_costs(config, small_env, masks, budget):
    _, dataset, graph = small_env
    policy = masks["random_high"]
    variants = [("E1_POSTFILTER", None), ("E2_BRIDGE", 2), ("E3_FIXED_TRACE", None)]
    for algorithm, r in variants:
        outcome = run_search(dataset.query_vectors[0], dataset.vectors, graph, config,
                             algorithm, budget, policy_mask=policy.mask, bridge_r=r)
        assert outcome.expanded_nodes <= budget
        assert outcome.unique_visited_nodes <= budget + 1
        assert outcome.distance_evaluations == outcome.unique_discovered_nodes
        assert outcome.neighbor_checks >= 0
        if budget == 0:
            assert outcome.distance_evaluations == 0
            assert outcome.returned_count == 0
            assert all(v is None for v in outcome.result_ids)


def test_12_prefix_derivation_matches_direct_budget_run(config, small_env, masks):
    _, dataset, graph = small_env
    policy = masks["random_high"]
    for algorithm, r in [("E1_POSTFILTER", None), ("E2_BRIDGE", 2), ("E3_FIXED_TRACE", None)]:
        full = run_log(dataset.query_vectors[0], dataset.vectors, graph, config, algorithm,
                       policy_mask=policy.mask, bridge_r=r, max_expansions=200)
        for budget in (1, 20, 100):
            derived = derive(full, config, budget, policy_mask=policy.mask)
            direct = run_search(dataset.query_vectors[0], dataset.vectors, graph, config,
                                algorithm, budget, policy_mask=policy.mask, bridge_r=r)
            for field in ("discovery_sequence", "visit_sequence", "expansion_sequence",
                          "distance_evaluations", "neighbor_checks", "expanded_nodes",
                          "result_ids", "termination_reason"):
                assert getattr(derived, field) == getattr(direct, field), (algorithm, budget, field)


def test_14_transfer_bytes_accounting():
    values = candidate_transfer_bytes(10, 128)
    assert values == {
        "candidate_id_bytes": 40,
        "candidate_meta_bytes": 80,
        "candidate_vector_bytes": 5160,
        "candidate_transfer_bytes": 80,
    }
