"""Tests for H1.2 independent-ACL stop-boundary generalization."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from pa_vfann.baseline_postfilter import adaptive_postfilter_from_plan  # noqa: E402

from experiments.run_h1_2_acl_generalization import (  # noqa: E402
    bootstrap_index_matrix,
    bootstrap_mean_ci,
    compute_acl_metrics,
    derive_acl_seeds,
    infer_last_node,
    make_acl_dataset_and_policy,
    mask_sha256,
    simulate_e1_stop,
)


def test_acl_seed_change_keeps_vector_and_query_array_objects(small_dataset, small_config):
    seed = derive_acl_seeds(small_config["data"]["seed"], "random", 5, count=1)[0]
    acl_dataset, policy = make_acl_dataset_and_policy(
        small_dataset, "random", 0.05, 40.0, 3, seed
    )
    assert acl_dataset.vectors is small_dataset.vectors
    assert acl_dataset.query_vectors is small_dataset.query_vectors
    assert acl_dataset.master_seed == int(seed)
    assert small_dataset.master_seed != int(seed)
    assert policy.actual_count == int(round(0.05 * small_dataset.n))


def test_acl_masks_are_reproducible_and_distinct(small_dataset):
    seeds = derive_acl_seeds(2026, "random", 5, count=30)
    assert len(set(seeds)) == 30
    _, first = make_acl_dataset_and_policy(small_dataset, "random", 0.05, 40.0, 3, seeds[0])
    _, first_again = make_acl_dataset_and_policy(
        small_dataset, "random", 0.05, 40.0, 3, seeds[0]
    )
    _, second = make_acl_dataset_and_policy(
        small_dataset, "random", 0.05, 40.0, 3, seeds[1]
    )
    assert mask_sha256(first.mask) == mask_sha256(first_again.mask)
    assert mask_sha256(first.mask) != mask_sha256(second.mask)


def test_simulate_e1_stop_boundaries_match_expected_semantics():
    path = tuple(range(6))
    at_floor = [False] * 6
    at_floor[path[1]] = True
    assert simulate_e1_stop(path, at_floor, k=1, min_visits=2, max_budget=6) == 2

    inside = [False] * 6
    inside[path[3]] = True
    assert simulate_e1_stop(path, inside, k=1, min_visits=2, max_budget=6) == 4

    exhausted = [False] * 6
    assert simulate_e1_stop(path, exhausted, k=1, min_visits=2, max_budget=6) == 6


def test_simulate_e1_stop_matches_frozen_e1_implementation():
    path = (5, 3, 9, 1, 7, 2, 8)
    mask = [False] * 10
    mask[9] = True
    bits = np.asarray(mask)
    outcome = adaptive_postfilter_from_plan(
        path, 0, 0, np.zeros(10), len(path), bits, 1, initial_budget=3, query_id=0
    )
    assert simulate_e1_stop(path, mask, k=1, min_visits=3, max_budget=len(path)) == (
        outcome.stop_position
    )


def test_attack_function_has_no_acl_parameter():
    params = set(inspect.signature(infer_last_node).parameters)
    assert params == {"public_path", "tau", "min_visits", "max_budget"}


def test_unique_nodes_and_duplicate_events_statistics():
    metrics = compute_acl_metrics(
        taus=[21, 22, 23, 24],
        inferred_nodes=[1, 2, 2, 3],
        authorized_count=5,
        n_queries=200,
        correct_events=4,
    )
    assert metrics["unique_nodes"] == 3
    assert metrics["duplicate_events"] == 1
    assert metrics["duplicate_event_rate"] == pytest.approx(0.25)
    assert metrics["informative_rate"] == pytest.approx(4 / 200)
    assert metrics["acl_coverage"] == pytest.approx(3 / 5)
    assert metrics["unique_yield"] == pytest.approx(3 / 4)
    assert metrics["precision"] == pytest.approx(1.0)


def test_unique_nodes_must_not_exceed_authorized_set():
    with pytest.raises(ValueError, match="metric invariant violated"):
        compute_acl_metrics(
            taus=[21, 22],
            inferred_nodes=[1, 2],
            authorized_count=1,
            n_queries=200,
            correct_events=2,
        )


def test_wrong_member_is_rejected_before_metrics():
    with pytest.raises(RuntimeError, match="precision invariant"):
        compute_acl_metrics(
            taus=[21, 22],
            inferred_nodes=[1, 2],
            authorized_count=5,
            n_queries=200,
            correct_events=1,
        )


def test_bootstrap_resamples_acl_units_not_queries():
    rng = np.random.default_rng(20261125)
    index = bootstrap_index_matrix(n_units=30, n_boot=10, rng=rng)
    assert index.shape == (10, 30)
    assert index.min() >= 0
    assert index.max() < 30


def test_bootstrap_mean_ci_is_deterministic_for_constant_values():
    mean, low, high = bootstrap_mean_ci(
        [0.42] * 30, rng=np.random.default_rng(7), n_boot=20
    )
    assert mean == pytest.approx(0.42)
    assert low == pytest.approx(0.42)
    assert high == pytest.approx(0.42)
