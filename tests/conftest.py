"""Small deterministic fixtures: same code paths, tiny problem size."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from pa_vfann.config import Config, default_config_path, load_config
from pa_vfann.dataset import build_dataset, squared_l2_to_all
from pa_vfann.graph import build_graph
from pa_vfann.policies import build_policy


@pytest.fixture(scope="session")
def small_config() -> Config:
    path = default_config_path()
    raw = copy.deepcopy(load_config(path).raw)
    raw["data"].update(n_vectors=200, dimension=16)
    raw["query"].update(n_queries=20)
    raw["graph"].update(degree=8, chunk_size=100)
    raw["search"].update(top_k=5, budgets=[0, 1, 5, 20, 50])
    raw["policies"].update(selectivities=[0.05])
    return Config(raw=raw, path=path)


@pytest.fixture(scope="session")
def small_dataset(small_config):
    return build_dataset(small_config)


@pytest.fixture(scope="session")
def small_graph(small_config, small_dataset):
    return build_graph(small_dataset, small_config)


@pytest.fixture(scope="session")
def small_qdist(small_config, small_dataset):
    return squared_l2_to_all(small_dataset.query_vectors, small_dataset.vectors)


@pytest.fixture(scope="session")
def policy_random(small_config, small_dataset):
    return build_policy(small_dataset, "random", 0.10, 40.0, 3)


@pytest.fixture(scope="session")
def policy_clustered(small_config, small_dataset):
    return build_policy(small_dataset, "clustered", 0.10, 15.0, 3)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
