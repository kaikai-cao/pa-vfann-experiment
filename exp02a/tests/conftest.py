"""EXP-02A test bootstrap: import audit package and frozen EXP-02 modules."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EXP02A = Path(__file__).resolve().parents[1]
ROOT = EXP02A.parent
for path in (str(EXP02A / "src"), str(ROOT / "exp02" / "src"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from pa_vfann_exp02a.config import load_config  # noqa: E402


@pytest.fixture(scope="module")
def audit_config():
    return load_config(EXP02A / "config" / "audit.yaml")


@pytest.fixture(scope="module")
def small_exp02_env():
    """Frozen EXP-02 smoke data, read only."""
    from pa_vfann_exp02.config import load_config as exp02_load
    from pa_vfann_exp02.exp01_bridge import build_dataset, build_graph, build_policy

    cfg = exp02_load(ROOT / "exp02" / "config" / "experiment_smoke.yaml")
    dataset = build_dataset(cfg)
    graph = build_graph(dataset, cfg)
    sigma = float(cfg["policies"]["clustered_sigma"])
    centers = int(cfg["policies"]["clustered_centers"])
    p1 = build_policy(dataset, "random", 0.01, sigma, centers)
    p2 = build_policy(dataset, "clustered", 0.30, sigma, centers)
    return cfg, dataset, graph, p1, p2
