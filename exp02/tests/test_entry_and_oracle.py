"""Tests 1-6: public entry, no distance oracle, lazy cache, GT isolation."""

from __future__ import annotations

import numpy as np
import pytest

from pa_vfann_exp02.algorithms import entry_from_seed, fixed_entry, run_log, run_search
from pa_vfann_exp02.config import Config
from pa_vfann_exp02 import lazy_search
from pa_vfann_exp02.ground_truth import build_ground_truth
from conftest import PoisonMask


def test_1_entry_literal_matches_seed(config):
    assert fixed_entry(config) == entry_from_seed(2026, 1000) == config["search"]["entry_node_id"]


def test_2_entry_independent_of_query_and_policy(config, small_env, masks):
    _, dataset, graph = small_env
    altered = Config(
        raw={**config.raw, "query": {**config.raw["query"], "n_queries": 999}},
        path=config.path,
    )
    assert fixed_entry(altered) == fixed_entry(config)

    traces = []
    for policy in masks.values():
        log = run_log(dataset.query_vectors[0], dataset.vectors, graph, config, "E3_FIXED_TRACE")
        assert log.entry_node == fixed_entry(config)
        traces.append((log.discovery_sequence, log.visit_sequence, log.expansion_sequence))
    assert traces[0] == traces[1] == traces[2]

    with pytest.raises(ValueError, match="must not receive a policy mask"):
        lazy_search.traverse(
            dataset.query_vectors[0], dataset.vectors, graph, fixed_entry(config), 100,
            mode="E3", policy_mask=PoisonMask(),
        )


def test_3_no_global_distance_precompute_in_search_sources():
    root = lazy_search.__file__
    import inspect
    from pathlib import Path

    for module_path in (Path(root), Path(root).with_name("algorithms.py")):
        source = module_path.read_text(encoding="utf-8")
        assert "squared_l2_to_all" not in source
        assert "np.argmin" not in source
        assert "@ vectors.T" not in source


def test_4_lazy_cache_computes_each_node_once(small_env):
    _, dataset, _ = small_env
    meter = lazy_search.DistanceMeter(dataset.query_vectors[0], dataset.vectors)
    values = [meter.get(11), meter.get(11), meter.get(3), meter.get(11)]
    assert meter.evaluations == 2
    assert set(meter.cache) == {11, 3}
    assert values[0] == values[1] == values[3]
    expected = float(np.dot(dataset.vectors[11] - dataset.query_vectors[0],
                            dataset.vectors[11] - dataset.query_vectors[0]))
    assert values[0] == pytest.approx(expected)


def test_5_distance_count_matches_actual_get_calls(config, small_env, masks, monkeypatch):
    _, dataset, graph = small_env

    class TrackingMeter(lazy_search.DistanceMeter):
        calls = 0

        def get(self, node_id):
            type(self).calls += 1
            return super().get(node_id)

    monkeypatch.setattr(lazy_search, "DistanceMeter", TrackingMeter)
    TrackingMeter.calls = 0
    log = run_log(dataset.query_vectors[0], dataset.vectors, graph, config, "E3_FIXED_TRACE",
                  max_expansions=100)
    assert TrackingMeter.calls == log.snapshots[-1].distance_evaluations
    assert log.snapshots[-1].distance_evaluations == len(log.discovery_sequence)


def test_6_ground_truth_cache_is_isolated(config, small_env, masks):
    _, dataset, graph = small_env
    gt = build_ground_truth(dataset.query_vectors[:2], dataset.vectors,
                            masks["random_high"].mask, 10)
    snapshot = gt.indices
    meter = lazy_search.DistanceMeter(dataset.query_vectors[0], dataset.vectors)
    assert meter.cache == {} and meter.evaluations == 0
    run_search(dataset.query_vectors[0], dataset.vectors, graph, config, "E3_FIXED_TRACE",
               100, policy_mask=masks["random_high"].mask)
    assert gt.indices == snapshot
    assert len(meter.cache) == 0
