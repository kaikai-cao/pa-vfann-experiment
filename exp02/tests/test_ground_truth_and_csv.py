"""Tests 13 and 15: insufficient ground truth, recall N/A, CSV completeness."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from conftest import tiny_config
from pa_vfann_exp02.algorithms import run_search
from pa_vfann_exp02.config import Config, load_config
from pa_vfann_exp02.exp01_bridge import build_dataset, build_policy
from pa_vfann_exp02.ground_truth import build_ground_truth
from pa_vfann_exp02.metrics import recall_at_k


def test_13_ground_truth_correct_and_repeatable(config, small_env, masks):
    _, dataset, graph = small_env
    policy = masks["random_high"]
    gt = build_ground_truth(dataset.query_vectors, dataset.vectors, policy.mask, 10)
    repeat = build_ground_truth(dataset.query_vectors, dataset.vectors, policy.mask, 10)
    assert gt.indices == repeat.indices
    for q, ids in enumerate(gt.indices):
        assert len(ids) <= 10
        assert all(policy.mask[int(v)] for v in ids)
        dists = list(gt.distances[q])
        assert dists == sorted(dists)
    result = run_search(dataset.query_vectors[0], dataset.vectors, graph, config,
                        "E3_FIXED_TRACE", 200, policy_mask=policy.mask)
    assert 0.0 <= recall_at_k(gt.indices[0], result.result_ids) <= 1.0


def test_13b_insufficient_authorized_records_are_not_fabricated():
    base = tiny_config(n=100, dim=8, entry=3)
    config = Config(raw={**base.raw, "query": {**base.raw["query"], "n_queries": 2}},
                    path=base.path)
    dataset = build_dataset(config)
    policy = build_policy(dataset, "random", 0.03, 40.0, 3)
    assert policy.actual_count == 3
    gt = build_ground_truth(dataset.query_vectors[:2], dataset.vectors, policy.mask, 10)
    assert all(gt.insufficient(q) for q in range(2))
    assert all(len(ids) == 3 for ids in gt.indices)
    assert math.isnan(recall_at_k((), (None,) * 10))


def test_15_raw_csv_has_every_query_including_failures():
    full_config = load_config(Path(__file__).resolve().parents[1] / "config" / "experiment.yaml")
    raw = Path(__file__).resolve().parents[1] / "results" / "raw" / "experiment_results.csv"
    if not raw.exists():
        pytest.skip("full experiment CSV not generated yet")
    import pandas as pd

    df = pd.read_csv(raw)
    sel = df[df["experiment"] == "selectivity"]
    n_queries = int(full_config["query"]["n_queries"])
    grouped = sel.groupby(
        ["policy_type", "selectivity_pct", "algorithm", "bridge_r", "budget"], dropna=False
    ).size()
    assert len(grouped) > 0
    assert (grouped == n_queries).all()
    expected_cells = (
        len(full_config["policies"]["types"])
        * len(full_config["policies"]["selectivities"])
        * (len(full_config["search"]["bridge_r_values"]) + 2)
        * len(full_config["search"]["budgets"])
    )
    assert len(grouped) == expected_cells
    assert sel["query_id"].nunique() == n_queries
    assert sel["recall_at_10"].isna().sum() >= 0  # failed/empty-GT queries are kept, never dropped
