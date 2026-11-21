import numpy as np

from pa_vfann.dataset import build_dataset, squared_l2_to_all


def test_dataset_reproducible(small_config):
    a = build_dataset(small_config)
    b = build_dataset(small_config)
    assert a.vectors.shape == (200, 16)
    assert a.query_vectors.shape == (20, 16)
    np.testing.assert_array_equal(a.vectors, b.vectors)
    np.testing.assert_array_equal(a.query_vectors, b.query_vectors)


def test_dataset_seed_changes_output(small_config):
    import copy
    from pa_vfann.config import Config

    raw = copy.deepcopy(small_config.raw)
    raw["data"]["seed"] = small_config.raw["data"]["seed"] + 1
    other = build_dataset(Config(raw, small_config.path))
    base = build_dataset(small_config)
    assert not np.array_equal(base.vectors, other.vectors)


def test_squared_l2_matches_direct(small_dataset):
    dist = squared_l2_to_all(small_dataset.query_vectors[:2], small_dataset.vectors)
    direct = np.sum((small_dataset.vectors[None, :, :] - small_dataset.query_vectors[:2, :, None].transpose(0, 2, 1)) ** 2, axis=2)
    np.testing.assert_allclose(dist, direct, rtol=1e-4, atol=1e-3)


def test_policies_have_requested_size_and_are_reproducible(small_dataset):
    from pa_vfann.policies import build_policy

    p1 = build_policy(small_dataset, "random", 0.10, 40.0, 3)
    p2 = build_policy(small_dataset, "random", 0.10, 40.0, 3)
    assert p1.actual_count == 20 == round(0.10 * small_dataset.n)
    np.testing.assert_array_equal(p1.mask, p2.mask)
    assert p1.actual_selectivity == p1.actual_count / small_dataset.n
