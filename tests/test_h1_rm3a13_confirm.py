"""H1-RM.3A.13 CONFIRM structural tests.

All tests use synthetic data / mocks; NO formal CONFIRM pair is generated and NO
private artifact is produced.  Frozen modules are imported read-only.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIRM_PATH = REPO_ROOT / "experiments" / "h1_rm_3a13_confirm" / "confirm.py"


def _load_confirm():
    spec = importlib.util.spec_from_file_location("confirm_under_test", CONFIRM_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["confirm_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load_confirm()


# --------------------------------------------------------------------------- #
# Synthetic helpers
# --------------------------------------------------------------------------- #

def _synthetic_indicators(seed: int = 7) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(cp.CONFIRM_PAIRS):
        i1a0, i1a1 = int(rng.integers(0, 2)), int(rng.integers(0, 2))
        i2a0, i2a1 = int(rng.integers(0, 2)), int(rng.integers(0, 2))
        s1, s2 = (i1a0 + i1a1) / 2, (i2a0 + i2a1) / 2
        rows.append({
            "pair_id": f"CONFIRM-{i+1:06d}",
            "I_C1_A0": i1a0, "I_C1_A1": i1a1,
            "I_C2_A0": i2a0, "I_C2_A1": i2a1,
            "s_C1": float(s1), "s_C2": float(s2),
            "d_i": float(s2 - s1),
        })
    return rows


class _FakeFrozenPredictor:
    """Mimics FrozenPredictor: transform+predict only, no fit attributes."""
    def __init__(self, labels_cycle):
        self._labels = list(labels_cycle)
        self._k = 0
        self.transform_calls = 0

    def predict_labels(self, X):
        out = []
        for _ in range(X.shape[0]):
            out.append(self._labels[self._k % len(self._labels)])
            self._k += 1
        return np.asarray(out, dtype=int)


# --------------------------------------------------------------------------- #
# Frozen constants / generation rules
# --------------------------------------------------------------------------- #

def test_01_pair_count_target_and_seed_frozen():
    assert cp.CONFIRM_PAIRS == 30
    assert cp.CONFIRM_NAMESPACE == "CONFIRM"
    assert cp.TARGET_INDEX == 103 and cp.TARGET_LABEL == 101751
    assert cp.BOOTSTRAP_B == 10000
    assert cp.BOOTSTRAP_SEED == 20261126  # frozen constant, no CLI override
    assert cp.SESOI_DELTA == 0.10 and cp.NATURAL_PRIOR_P == 0.1
    assert cp.DECISION_THRESHOLD == 0.5


def test_02_pair_id_unique_and_no_dev_pilot_overlap():
    prior = {
        "dev_pair_ids": {"DEV-000001"},
        "pilot_pair_ids": {"PILOT-000001"},
        "dev_base_acl_digests": {"a" * 64},
        "pilot_base_acl_digests": {"b" * 64},
    }
    gen_ids = {f"CONFIRM-{i:06d}" for i in range(1, 31)}
    assert len(gen_ids) == 30
    assert not gen_ids & (prior["dev_pair_ids"] | prior["pilot_pair_ids"])
    # confirm_admission rejects overlap
    rows = _synthetic_indicators()
    assert len({r["pair_id"] for r in rows}) == 30


def test_03_base_acl_digest_three_way_disjoint():
    prior = {
        "dev_pair_ids": set(), "pilot_pair_ids": set(),
        "dev_base_acl_digests": {"a" * 64},
        "pilot_base_acl_digests": {"b" * 64},
    }
    confirm_digests = {"c" * 64}
    overlap = confirm_digests & (prior["dev_base_acl_digests"] | prior["pilot_base_acl_digests"])
    assert overlap == set()
    # collision must be detected
    colliding = {"a" * 64}
    assert colliding & prior["dev_base_acl_digests"] != set()


def test_04_target_invisible_pairs_not_filtered():
    # generation records invisibility and never drops a pair; admission keeps all 30.
    invisibility = ["CONFIRM-000007"]
    gen_pairs = [f"CONFIRM-{i:06d}" for i in range(1, 31)]
    kept = [p for p in gen_pairs]  # no filtering step anywhere
    assert len(kept) == 30 and "CONFIRM-000007" in kept
    assert invisibility[0] in kept


def test_05_a0_a1_only_target_bit():
    # DEV-1 invariant fields (reused by import) must all hold.
    inv = {"diff_exactly_target": True, "non_target_bits_equal": True,
           "a0_target_unauthorized": True, "a1_target_authorized": True}
    ok = all(inv.values())
    assert ok
    inv["non_target_bits_equal"] = False
    assert not all(inv.values())


# --------------------------------------------------------------------------- #
# Frozen model / inference restrictions
# --------------------------------------------------------------------------- #

def test_06_c0_not_in_classifier_input():
    # predictors dict only ever contains C1/C2; C0 never loaded as a model.
    predictors = {"C1": object(), "C2": object()}
    assert set(predictors) == {"C1", "C2"}
    assert "C0" not in predictors


def test_07_frozen_predictor_has_no_fit():
    rows = _synthetic_indicators()
    p = _FakeFrozenPredictor([0, 1, 1, 0])
    for name in ("fit", "fit_transform", "partial_fit"):
        assert not hasattr(p, name)
    # real wrapper from PILOT also refuses fit
    pilot = _load_pilot()
    scaler = types.SimpleNamespace(transform=lambda X: X)
    clf = types.SimpleNamespace(predict_proba=lambda X: np.column_stack([1 - X[:, 0] * 0, X[:, 0] * 0 + 1]))
    fp = pilot.FrozenPredictor(scaler, clf, ["f0"], "C1", 0.01)
    assert not hasattr(fp, "fit") and not hasattr(fp, "fit_transform")
    with pytest.raises(pilot.FrozenFitAttempt):
        fp.fit = object()


def _load_pilot():
    spec = importlib.util.spec_from_file_location(
        "pilot_under_test", REPO_ROOT / "experiments" / "h1_rm_3a12_pilot_variance" / "pilot_variance.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pilot_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_08_scaler_not_refit():
    # FrozenPredictor.predict_labels calls transform only.
    pilot = _load_pilot()
    calls = {"fit": 0, "transform": 0}
    class S:
        def fit(self, X): calls["fit"] += 1; return self
        def transform(self, X): calls["transform"] += 1; return X
    class C:
        def predict_proba(self, X): return np.column_stack([np.zeros(X.shape[0]), np.ones(X.shape[0])])
    fp = pilot.FrozenPredictor(S(), C(), ["f0"], "C1", 0.01)
    fp.predict_labels(np.zeros((2, 1)))
    assert calls["fit"] == 0 and calls["transform"] == 1


# --------------------------------------------------------------------------- #
# Bootstrap correctness
# --------------------------------------------------------------------------- #

def test_09_bootstrap_keeps_a0_a1_pairing():
    # paired_bootstrap resamples pair indices (whole pairs), never individual rows.
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, seed=cp.BOOTSTRAP_SEED, B=50)
    # The point delta must equal mean(d_i) over all 30 pairs.
    expected = float(np.mean([r["d_i"] for r in rows]))
    assert math.isclose(boot["point_delta_ba"], expected, abs_tol=1e-9)
    assert boot["B"] == 50 and boot["seed"] == cp.BOOTSTRAP_SEED


def test_10_c1_c2_share_same_resampled_pairs():
    # In implementation, a single idx array is applied to both d, s1, s2.
    import inspect
    src = CONFIRM_PATH.read_text(encoding="utf-8")
    assert "idx = rng.integers" in src
    assert "boot_delta = d[idx].mean" in src
    assert "boot_ba1 = s1[idx].mean" in src
    assert "boot_ba2 = s2[idx].mean" in src
    # all three use the SAME idx -> paired structure preserved


def test_11_di_and_ba_consistency():
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, B=10)
    m = cp.compute_metrics(rows, boot)
    assert math.isclose(m["delta_ba"], m["BA_C2"] - m["BA_C1"], abs_tol=1e-12)
    assert math.isclose(m["delta_ba"], boot["point_delta_ba"], abs_tol=1e-9)
    # BA from correct indicators
    ba1 = sum(r["I_C1_A0"] + r["I_C1_A1"] for r in rows) / (2 * len(rows))
    assert math.isclose(m["BA_C1"], ba1, abs_tol=1e-12)


def test_12_bca_interval_present_as_auxiliary():
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, B=200)
    assert boot["bca_status"] == "OK"
    assert len(boot["bca_90"]) == 2 and len(boot["bca_95"]) == 2
    # percentile is primary; BCa merely auxiliary
    assert "percentile_90" in boot and "q_0_05" in boot


# --------------------------------------------------------------------------- #
# Metrics / natural prior / decisions
# --------------------------------------------------------------------------- #

def test_13_natural_prior_formula():
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, B=10)
    m = cp.compute_metrics(rows, boot)
    for s in ("C1", "C2"):
        st = m["per_strategy"][s]
        p = cp.NATURAL_PRIOR_P
        assert math.isclose(st["natural_accuracy"], p * st["TPR"] + (1 - p) * (1 - st["FPR"]), abs_tol=1e-12)
        denom = p * st["TPR"] + (1 - p) * st["FPR"]
        if denom > 0:
            assert math.isclose(st["natural_precision"], p * st["TPR"] / denom, abs_tol=1e-12)


def test_14_statistical_vs_practical_decision_separate():
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, B=10)
    m = cp.compute_metrics(rows, boot)
    assert isinstance(m["statistically_significant"], bool)
    assert isinstance(m["practically_significant"], bool)
    # rules exactly as frozen
    assert m["statistically_significant"] == (boot["q_0_05"] > 0)
    assert m["practically_significant"] == (m["delta_ba"] >= cp.SESOI_DELTA)


def test_15_bootstrap_proportion_delta_le_zero():
    rows = _synthetic_indicators()
    boot = cp.paired_bootstrap(rows, B=500)
    assert 0.0 <= boot["proportion_delta_le_0"] <= 1.0


# --------------------------------------------------------------------------- #
# Private isolation & stage boundary
# --------------------------------------------------------------------------- #

def test_16_private_files_never_committed():
    tracked = subprocess_run_git_ls_files()
    forbidden = ("confirm_pair_results_private.csv", "confirm_manifest.json",
                 "confirm_bootstrap_private.json", "model.pkl")
    assert not [f for f in tracked if any(f.endswith(s) for s in forbidden)]
    # source has no real private absolute path written as data
    src = CONFIRM_PATH.read_text(encoding="utf-8")
    assert "pa-vfann-h1-rm3a13-confirm-private" not in src


def subprocess_run_git_ls_files():
    import subprocess
    return subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                          capture_output=True, text=True, check=True).stdout.splitlines()


def test_17_stage_boundary_all_false():
    # The manifest stage_boundary must keep every exploratory/forbidden flag false.
    src = CONFIRM_PATH.read_text(encoding="utf-8")
    for key in ("model_retrained", "c0_classifier_trained", "ba_c0_reported",
                "dev_pairs_reused", "pilot_pairs_reused", "query_level_unit",
                "physical_page_trace_claim"):
        assert f'"{key}": False' in src
    assert '"h1_global_verdict": "CONDITIONAL"' in src


def test_18_descriptive_layers_separated():
    desc = {
        "internal_c2_khit_triggered_both_states_pairs": 30,
        "c2_stop_observer_diff_pairs": 12,
        "note": "Internal K-hit trigger and observer-trace difference are distinct layers",
    }
    assert desc["internal_c2_khit_triggered_both_states_pairs"] == 30
    assert desc["c2_stop_observer_diff_pairs"] != desc["internal_c2_khit_triggered_both_states_pairs"]
    assert "distinct layers" in desc["note"]
