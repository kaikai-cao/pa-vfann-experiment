import numpy as np
import pytest

from pa_vfann.ground_truth import filtered_exact_topk


def test_ground_truth_only_authorized_sorted_bounded(small_qdist, policy_random, small_config):
    gt = filtered_exact_topk(small_qdist, policy_random.mask, small_config["search"]["top_k"])
    legal = set(np.flatnonzero(policy_random.mask).tolist())
    assert gt.n_queries == small_qdist.shape[0]
    for q in range(gt.n_queries):
        ids = gt.indices[q]
        assert len(ids) <= small_config["search"]["top_k"]
        assert set(ids) <= legal
        dists = gt.distances[q]
        assert list(dists) == sorted(dists)
        assert all(dist == pytest.approx(small_qdist[q, idx]) for dist, idx in zip(dists, ids))


def test_ground_truth_reproducible(small_qdist, policy_random, small_config):
    k = small_config["search"]["top_k"]
    a = filtered_exact_topk(small_qdist, policy_random.mask, k)
    b = filtered_exact_topk(small_qdist, policy_random.mask, k)
    assert a == b


def test_ground_truth_insufficient_authorization(small_qdist, small_config):
    n = small_qdist.shape[1]
    mask = np.zeros(n, dtype=bool)
    mask[[3, 9]] = True
    gt = filtered_exact_topk(small_qdist, mask, small_config["search"]["top_k"])
    assert all(len(ids) == 2 for ids in gt.indices)
    assert all(gt.insufficient(q) for q in range(gt.n_queries))
    assert gt.authorized_counts[0] == 2


def test_ground_truth_does_not_depend_on_search(small_qdist, policy_clustered, small_config):
    gt = filtered_exact_topk(small_qdist, policy_clustered.mask, small_config["search"]["top_k"])
    legal = set(np.flatnonzero(policy_clustered.mask).tolist())
    for q in range(gt.n_queries):
        exact = sorted(legal, key=lambda idx: (small_qdist[q, idx], idx))[: small_config["search"]["top_k"]]
        assert list(gt.indices[q]) == exact
