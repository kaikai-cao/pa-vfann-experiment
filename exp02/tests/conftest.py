"""EXP-02 test fixtures (self-contained path bootstrap)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EXP02 = Path(__file__).resolve().parents[1]
ROOT = EXP02.parent
for path in (str(EXP02 / "src"), str(ROOT / "src"), str(EXP02 / "experiments")):
    if path not in sys.path:
        sys.path.insert(0, path)

from pa_vfann_exp02.config import Config, load_config  # noqa: E402
from pa_vfann_exp02.exp01_bridge import build_dataset, build_graph, build_policy  # noqa: E402


class PoisonMask:
    """An authorization object that raises on ANY read; E3 must never touch it."""

    def __getitem__(self, key):
        raise AssertionError("E3 search read an authorization bit")

    def __array__(self, *args, **kwargs):
        raise AssertionError("E3 search converted an authorization mask")

    def __bool__(self):
        raise AssertionError("E3 search tested an authorization mask")

    def __len__(self):
        raise AssertionError("E3 search measured an authorization mask")


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(EXP02 / "config" / "experiment_smoke.yaml")


@pytest.fixture(scope="module")
def small_env(config):
    dataset = build_dataset(config)
    graph = build_graph(dataset, config)
    return config, dataset, graph


@pytest.fixture(scope="module")
def masks(config, small_env):
    _, dataset, _ = small_env
    sigma = float(config["policies"]["clustered_sigma"])
    centers = int(config["policies"]["clustered_centers"])
    return {
        "random_low": build_policy(dataset, "random", 0.01, sigma, centers),
        "random_high": build_policy(dataset, "random", 0.30, sigma, centers),
        "clustered": build_policy(dataset, "clustered", 0.10, sigma, centers),
    }


def tiny_config(n: int = 4, dim: int = 2, entry: int = 0) -> Config:
    base = load_config(EXP02 / "config" / "experiment_smoke.yaml")
    raw = {
        **base.raw,
        "data": {**base.raw["data"], "n_vectors": n, "dimension": dim},
        "query": {**base.raw["query"], "n_queries": 1},
        "search": {**base.raw["search"], "budgets": [1, 2, 4], "entry_node_id": entry},
    }
    return Config(raw=raw, path=base.path)
