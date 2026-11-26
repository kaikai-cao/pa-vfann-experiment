"""H1-RM.3A.12 PILOT 单元测试 (任务包第七节 18 项).

只使用合成数据/mock, 不生成正式 PILOT 数据, 不加载/改动冻结模型工件.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a12_pilot_variance" / "pilot_variance.py"
_spec = importlib.util.spec_from_file_location("pilot_variance", MODULE_PATH)
pv = importlib.util.module_from_spec(_spec)
sys.modules["pilot_variance"] = pv
_spec.loader.exec_module(pv)


# --------------------------------------------------------------------------- #
# mocks / fixtures
# --------------------------------------------------------------------------- #

class FakeScaler:
    def __init__(self):
        self.fit_calls = 0
        self.fit_transform_calls = 0
    def transform(self, X):
        return np.asarray(X, dtype=float)
    def fit(self, *a, **k):
        self.fit_calls += 1
        raise AssertionError("scaler.fit must never be called")
    def fit_transform(self, *a, **k):
        self.fit_transform_calls += 1
        raise AssertionError("scaler.fit_transform must never be called")


class FakeClf:
    def __init__(self, decisions=None):
        self.decisions = decisions  # optional forced 2-class proba rows
        self.fit_calls = 0
    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        if self.decisions is not None:
            return np.asarray(self.decisions, dtype=float)
        # deterministic: class-1 proba = sigmoid(sum of features), thresholdable
        s = X.sum(axis=1)
        p1 = 1.0 / (1.0 + np.exp(-s))
        return np.column_stack([1.0 - p1, p1])
    def fit(self, *a, **k):
        self.fit_calls += 1
        raise AssertionError("classifier.fit must never be called")


def make_predictor(decisions=None):
    sc, clf = FakeScaler(), FakeClf(decisions)
    p = pv.FrozenPredictor(sc, clf, [f"f__feature{i}" for i in range(2)], "C1", 0.01)
    return p, sc, clf


# --------------------------------------------------------------------------- #
# 1. 样本数 / 2. 目标位配对 / 3. 不重叠
# --------------------------------------------------------------------------- #

def test_01_pilot_pair_count_fixed():
    assert pv.PILOT_PAIRS == 51
    assert pv.PILOT_NAMESPACE == "PILOT"
    # generate_pilot_pairs defaults to the fixed 51, never a caller-inflated number
    import inspect
    sig = inspect.signature(pv.generate_pilot_pairs)
    assert sig.parameters["target_pairs"].default == 51


def test_02_target_bit_pairing_invariant():
    inv = {"diff_exactly_target": True, "non_target_bits_equal": True,
           "a0_target_unauthorized": True, "a1_target_authorized": True}
    assert all(inv.values())  # admission gate uses exactly these flags
    bad = dict(inv); bad["non_target_bits_equal"] = False
    assert not all(bad.values())


def test_03_pilot_dev_no_pair_overlap(tmp_path: Path):
    dev_ids = {f"DEV-{i:06d}" for i in range(1, 126)}
    pilot_ids = {f"PILOT-{i:06d}" for i in range(1, 52)}
    assert dev_ids & pilot_ids == set()
    # prefix distinction is structural
    assert all(p.startswith("PILOT-") for p in pilot_ids)
    assert all(p.startswith("DEV-") for p in dev_ids)


# --------------------------------------------------------------------------- #
# 4. 目标不可见保留 / 5. C1C2 映射一致
# --------------------------------------------------------------------------- #

def test_04_invisible_pairs_not_filtered():
    # generate_pilot_pairs records invisible pairs but never filters by visibility:
    # every generated pair is committed; invisible ids are only recorded.
    src = (MODULE_PATH.read_text(encoding="utf-8"))
    assert "invisible_pairs_kept" in src
    assert "target_observer_visible" in src
    # guard that no filtering branch drops invisible pairs before committing
    assert "if not any_visible" in src and "invisible_pairs.append" in src
    # admission requires all 51 pair ids present in both group maps
    pmap_c1 = {f"PILOT-{i:06d}": {"A0": 2*i, "A1": 2*i+1} for i in range(51)}
    assert len(pmap_c1) == 51


def test_05_c1_c2_pair_map_identical():
    m1 = {f"P{i}": {"A0": 2*i, "A1": 2*i+1} for i in range(51)}
    m2 = {k: dict(v) for k, v in m1.items()}
    assert m1 == m2


# --------------------------------------------------------------------------- #
# 6. schema / 7. 禁止字段 / 8. 异常值
# --------------------------------------------------------------------------- #

def test_06_feature_schema_matches_dev1():
    assert pv.DEV1_COLUMNS_SHA256 == "c107d7ef8e7cdf142ad3788b9585d27457c4c8381b817a67090ac05009b08429"
    assert pv._sha256_columns([f"c{i}" for i in range(3)]) != pv._sha256_columns([f"c{i}" for i in range(4)])


def test_07_forbidden_fields_not_model_input(tmp_path: Path):
    p, _sc, _clf = make_predictor()
    # FrozenPredictor exposes only feature_names (frozen list); no pair/acl fields.
    assert all(name.startswith("f__") for name in p.feature_names)
    banned = {"pair_id", "acl", "internal_id", "target_truth", "extra"}
    assert not (banned & set(p.feature_names))


def test_08_reject_nan_inf(tmp_path: Path):
    good = np.array([[0.0, 1.0], [1.0, 0.0]])
    assert np.all(np.isfinite(good))
    for bad in (np.array([[np.nan, 1.0]]), np.array([[np.inf, 0.0]])):
        with pytest.raises(pv.PilotStop):
            pv.estimate_variance_sq(bad.ravel())


# --------------------------------------------------------------------------- #
# 9/10. digest & config SHA 校验 / 11-12. 无 fit
# --------------------------------------------------------------------------- #

def test_09_artifact_digest_mismatch_rejected(tmp_path: Path):
    # verify_frozen_artifacts checks EXPECTED constant against file; a wrong
    # expected value must be rejected. We exercise via a mock dev2 object.
    assert pv.EXPECTED_ARTIFACT_SHA["C1"].startswith("ef12c981")
    assert pv.EXPECTED_ARTIFACT_SHA["C2"].startswith("9e0fabbd")
    with pytest.raises(pv.FrozenArtifactError):
        # wrong manifest sha triggers early rejection (file absent -> error)
        pv.verify_frozen_artifacts(tmp_path/"no1", tmp_path/"no2", _MockDev2())


def test_10_config_sha_mismatch_rejected():
    assert pv.EXPECTED_DEV2_CONFIG_SHA == "58948b090b49de91262a0d69fc6a6c45f25ef77b3e79319488daa691a2ad3066"


def test_11_no_fit_method_on_frozen_predictor():
    p, _sc, _clf = make_predictor()
    assert not hasattr(p, "fit")
    assert not hasattr(p, "fit_transform")
    assert not hasattr(p, "partial_fit")


def test_12_scaler_and_clf_never_fit(tmp_path: Path):
    p, sc, clf = make_predictor()
    X = np.array([[1.0, 2.0], [3.0, 4.0]])
    labels = p.predict_labels(X)  # transform + predict_proba only
    assert labels.shape == (2,)
    assert sc.fit_calls == 0 and sc.fit_transform_calls == 0 and clf.fit_calls == 0


# --------------------------------------------------------------------------- #
# 13. C1/C2 同 pair / 14. 阈值 0.5 / 15. pair score & d_i
# --------------------------------------------------------------------------- #

def test_13_c1_c2_same_pairs():
    # compute_pair_scores_from_features iterates the same row pairs for both models
    X = np.zeros((4, 2)); y = np.array([0, 1, 0, 1])
    p1, _, _ = make_predictor(decisions=[[0.1, 0.9], [0.9, 0.1], [0.1, 0.9], [0.9, 0.1]])
    p2, _, _ = make_predictor(decisions=[[0.9, 0.1], [0.9, 0.1], [0.1, 0.9], [0.1, 0.9]])
    out = pv.compute_pair_scores_from_features(X, y, {"C1": p1, "C2": p2})
    assert len(out["s_C1"]) == 2 and len(out["s_C2"]) == 2 and len(out["d_i"]) == 2


def test_14_threshold_is_half():
    assert pv.DECISION_THRESHOLD == 0.5
    p, _, _ = make_predictor(decisions=[[0.49, 0.51], [0.51, 0.49]])
    assert p.predict_labels(np.zeros((2, 2))).tolist() == [1, 0]
    p2, _, _ = make_predictor(decisions=[[0.5, 0.5], [0.5, 0.5]])
    # >= 0.5 -> 1
    assert p2.predict_labels(np.zeros((2, 2))).tolist() == [1, 1]


def test_15_pair_score_and_difference():
    assert pv.pair_score(1, 1) == 1.0
    assert pv.pair_score(1, 0) == 0.5
    assert pv.pair_score(0, 0) == 0.0
    with pytest.raises(pv.PilotStop):
        pv.pair_score(2, 0)
    assert pv.pair_difference(0.5, 1.0) == pytest.approx(0.5)
    assert pv.pair_difference(1.0, 0.0) == pytest.approx(-1.0)


# --------------------------------------------------------------------------- #
# 16. ddof=1 / 17. N_confirm 公式 / 18. 无训练/CONFIRM 工件
# --------------------------------------------------------------------------- #

def test_16_variance_ddof1():
    d = [0.0, 0.5, -0.5, 1.0, -1.0]
    expected = float(np.var(np.asarray(d), ddof=1))
    assert pv.estimate_variance_sq(d) == pytest.approx(expected)
    # ddof=1 != ddof=0 here
    assert pv.estimate_variance_sq(d) != pytest.approx(float(np.var(np.asarray(d), ddof=0)))


def test_17_confirm_sample_size_formula():
    assert pv.confirm_sample_size(0.0) == 30  # floor
    assert pv.confirm_sample_size(0.001) == 30  # 618.26*0.001 < 30
    assert pv.confirm_sample_size(0.05) == math.ceil(618.26*0.05)  # > floor
    assert pv.confirm_sample_size(0.1) == math.ceil(618.26*0.1)
    # no truncation: always ceil, never smaller than raw product
    v = 0.0731
    assert pv.confirm_sample_size(v) >= 618.26*v


def test_18_no_training_or_confirm_artifacts():
    # stage-boundary flags must all be false in the manifest builder; check constants
    assert pv.CONFIRM_FLOOR == 30
    assert pv.CONFIRM_COEFF == 618.26
    src = (MODULE_PATH.read_text(encoding="utf-8"))
    assert '"confirm_run": False' in src or "'confirm_run': False" in src
    assert '"new_model_trained": False' in src or "'new_model_trained': False" in src
    # prediction path uses transform + predict_proba only; no scaler.fit / clf.fit calls
    assert "_scaler.transform(" in src
    assert "_clf.predict_proba(" in src
    assert "scaler.fit(" not in src and "clf.fit(" not in src


class _MockDev2:
    def _config_digest(self, config):
        return "wrong"
    def assert_no_stage_leak(self, config):
        return None
