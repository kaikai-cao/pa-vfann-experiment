"""H1-RM.3A.11 DEV-2 单元测试 (任务包第九节 16 项).

测试只使用仓库内代码 + 临时合成数据; 真实 DEV 数据准入另由正式运行验证.
不运行 PILOT / CONFIRM, 不计算确认性统计.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a11_dev2_model_freeze" / "dev2_model_freeze.py"

_spec = importlib.util.spec_from_file_location("dev2_model_freeze", MODULE_PATH)
dp = importlib.util.module_from_spec(_spec)
sys.modules["dev2_model_freeze"] = dp
_spec.loader.exec_module(dp)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _make_pair_ids(n: int = 125) -> list[str]:
    return [f"DEV-{i:06d}" for i in range(1, n + 1)]


def _synthetic_arrays(n_pairs: int = 125, dim: int = 117, seed: int = 7):
    """构造 A0/A1 成对、标签平衡的合成 bundle."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n_pairs * 2, dim), dtype=np.float64)
    y = np.zeros(n_pairs * 2, dtype=np.int64)
    pair_ids: list[str] = []
    for i in range(n_pairs):
        base = rng.normal(0, 1, dim)
        X[2 * i] = base
        X[2 * i + 1] = base + rng.normal(0.35, 0.2, dim)
        y[2 * i], y[2 * i + 1] = 0, 1
        pair_ids.extend([f"DEV-{i + 1:06d}"] * 2)
    return X, y, np.asarray(pair_ids)


@pytest.fixture(scope="module")
def config() -> dict:
    return dp.build_frozen_config()


# ---------------------------------------------------------------------------
# 1-4. 数据准入 / pair 一致性 / 同折 / 每折 pair 数
# ---------------------------------------------------------------------------

def test_01_dev_data_rows_labels_pairs(tmp_path: Path):
    """真实 DEV-1 数据准入: 250 行 / 125 pair / 各 125 标签."""
    dev_root = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
    if not (dev_root / "manifest.json").exists():
        pytest.skip("DEV-1 私有数据不可用")
    validation = dp.validate_inputs(dev_root)
    assert validation["status"] == "PASS"
    for s in dp.STRATEGIES:
        v = validation["strategies"][s]
        assert v["rows"] == 250
        assert len(v["pair_ids"]) == 125
        assert v["labels"].count("0") == 125
        assert v["labels"].count("1") == 125
        for pid in v["pair_ids"]:
            assert set(v["pair_to_rows"][pid]) == {"A0", "A1"}


def test_02_c1_c2_pair_sets_identical(tmp_path: Path):
    dev_root = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
    if not (dev_root / "manifest.json").exists():
        pytest.skip("DEV-1 私有数据不可用")
    validation = dp.validate_inputs(dev_root)
    assert validation["strategies"]["C1"]["pair_ids"] == validation["strategies"]["C2"]["pair_ids"]
    assert validation["pair_sets_identical"] is True
    assert validation["grouping_maps_identical"] is True


def test_03_a0_a1_same_fold():
    pair_ids = []
    for pid in _make_pair_ids():
        pair_ids.extend([pid, pid])
    folds = dp.build_folds(pair_ids)
    for fold in folds:
        for pid in fold["val_pair_ids"]:
            assert fold["val_pair_ids"].count(pid) == 1
            assert pid not in fold["train_pair_ids"]
            rows = [i for i in fold["val_row_indices"] if pair_ids[i] == pid]
            assert len(rows) == 2  # A0 与 A1 同为验证行


def test_04_fold_pair_counts():
    pair_ids = []
    for pid in _make_pair_ids():
        pair_ids.extend([pid, pid])
    folds = dp.build_folds(pair_ids)
    assert len(folds) == 5
    for fold in folds:
        assert fold["val_pairs"] == 25
        assert fold["train_pairs"] == 100
        assert fold["val_rows"] == 50
        assert fold["train_rows"] == 200


# ---------------------------------------------------------------------------
# 5. 标准化只在训练 fold 拟合
# ---------------------------------------------------------------------------

def test_05_scaler_fit_only_on_train_fold(config: dict):
    X, y, pair_ids = _synthetic_arrays()
    folds = dp.build_folds(pair_ids)
    fold = folds[0]
    m = dp.cv_fold_metrics(X, y, fold["train_row_indices"], fold["val_row_indices"], 1.0, config)
    import hashlib
    expected = hashlib.sha256(
        np.asarray(sorted(fold["train_row_indices"])).tobytes()
    ).hexdigest()
    assert m["scaler_fit_row_indices_sha256"] == expected
    assert m["scaler_fitted_on_all_rows"] is False
    # scaler mean 只能等于训练行均值, 不等于全数据均值
    train_mean = X[fold["train_row_indices"]].mean(axis=0)[:3].tolist()
    assert np.allclose(m["scaler_mean_first3"], train_mean)


# ---------------------------------------------------------------------------
# 6-8. schema digest / 缺失值拒绝 / pair ID 不入模型
# ---------------------------------------------------------------------------

def test_06_feature_schema_digest():
    dev_root = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
    if not (dev_root / "manifest.json").exists():
        pytest.skip("DEV-1 私有数据不可用")
    validation = dp.validate_inputs(dev_root)
    for s in dp.STRATEGIES:
        assert validation["strategies"][s]["feature_columns_sha256"] == dp.DEV1_COLUMNS_SHA256
        assert len(validation["strategies"][s]["header"]) - 1 == 117


def test_07_reject_missing_nan_inf(tmp_path: Path):
    header = [f"f{i}" for i in range(3)] + ["label"]
    good = [["1.0", "2.0", "3.0", "0"], ["4.0", "5.0", "6.0", "1"]]
    dp._check_finite_features(header, good, Path("good.csv"))
    for bad in (
        [["", "2.0", "3.0", "0"]],
        [["nan", "2.0", "3.0", "0"]],
        [["1.0", "inf", "3.0", "0"]],
    ):
        with pytest.raises(dp.DataAdmissionError):
            dp._check_finite_features(header, bad, Path("bad.csv"))


def test_08_pair_id_not_model_input(config: dict):
    cfg = dp.build_frozen_config()
    assert cfg["input_dim"] == 117
    dev_root = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
    if (dev_root / "manifest.json").exists():
        validation = dp.validate_inputs(dev_root)
        X, y, pair_ids, names = dp.arrays_from_validation(validation["strategies"]["C1"])
        assert X.shape == (250, 117)
        assert not any("pair" in n.lower() for n in names)
        clf = dp.make_estimator(1.0, config)
        clf.fit(X, y)
        assert clf.n_features_in_ == 117


# ---------------------------------------------------------------------------
# 9-12. 五个 C / 平均 BA 选择 / tie-break / C1 C2 分别选择
# ---------------------------------------------------------------------------

def test_09_all_five_C_executed(config: dict):
    X, y, pair_ids = _synthetic_arrays()
    cv, folds = dp.run_cv(X, y, pair_ids, config)
    assert set(cv["by_C"].keys()) == {"0.01", "0.1", "1.0", "10.0", "100.0"}
    for entry in cv["by_C"].values():
        assert len(entry["folds"]) == 5
        assert all(f["C"] == entry["C"] for f in entry["folds"])


def test_10_selection_max_mean_ba(config: dict):
    X, y, pair_ids = _synthetic_arrays()
    cv, _ = dp.run_cv(X, y, pair_ids, config)
    chosen_C, entry = dp.select_c(cv)
    means = {c: e["mean_ba"] for c, e in cv["by_C"].items()}
    assert entry["mean_ba"] == pytest.approx(max(means.values()))
    assert chosen_C in dp.C_GRID


def test_11_tie_break_smaller_C():
    cv = {"by_C": {}}
    for C in dp.C_GRID:
        cv["by_C"][str(C)] = {"C": C, "mean_ba": 0.6, "folds": []}
    chosen_C, _ = dp.select_c(cv)
    assert chosen_C == min(dp.C_GRID)


def test_12_c1_c2_selected_separately(config: dict):
    X, y, pid = _synthetic_arrays()
    cv1, _ = dp.run_cv(X, y, pid, config)
    # 用不同信号强度制造不同最优 C
    X2 = X.copy()
    X2[:, 0] += 5.0
    cv2, _ = dp.run_cv(X2, y, pid, config)
    c1, _ = dp.select_c(cv1)
    c2, _ = dp.select_c(cv2)
    assert c1 in dp.C_GRID and c2 in dp.C_GRID


# ---------------------------------------------------------------------------
# 13-14. 全数据重拟合 scaler / 保存加载预测一致
# ---------------------------------------------------------------------------

def test_13_final_refit_scaler_full_dev(config: dict, tmp_path: Path):
    X, y, _ = _synthetic_arrays()
    scaler, clf, info = dp.train_final_model(X, y, 1.0, config)
    assert info["scaler_refit_on_full_dev"] is True
    assert info["train_rows"] == 250
    assert info["train_pairs"] == 125
    assert np.allclose(scaler.mean_, X.mean(axis=0))
    assert clf.n_features_in_ == 117


def test_14_save_load_predict_identical(config: dict, tmp_path: Path):
    X, y, _ = _synthetic_arrays()
    scaler, clf, _ = dp.train_final_model(X, y, 1.0, config)
    metadata = {"strategy": "C1", "feature_dim": 117}
    save_info = dp.save_model_artifact(tmp_path / "C1_model", scaler, clf, metadata)
    loaded_scaler, loaded_clf, loaded_meta = dp.load_model_artifact(tmp_path / "C1_model")
    probe = dp.fixed_probe_inputs()
    pre = dp.predict_with(scaler, clf, probe)
    post = dp.predict_with(loaded_scaler, loaded_clf, probe)
    assert pre == post
    assert loaded_meta["model_artifact_sha256"] == save_info["artifact_sha256"]
    assert np.allclose(loaded_clf.coef_, clf.coef_)


# ---------------------------------------------------------------------------
# 15-16. 配置冻结不可覆盖 / 阶段边界
# ---------------------------------------------------------------------------

def test_15_config_frozen_no_runtime_override(tmp_path: Path):
    cfg, sha = dp.freeze_config(tmp_path)
    assert dp.load_frozen_config(tmp_path, sha)["config_sha256"] == sha
    # 事后篡改配置必须被拒绝
    cfg["estimator_params"]["tol"] = 1e-4
    (tmp_path / "frozen_training_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(dp.ConfigFrozenError):
        dp.load_frozen_config(tmp_path, sha)
    # 直接传入被改动的 estimator_params 也必须拒绝
    with pytest.raises(dp.ConfigFrozenError):
        dp.make_estimator(1.0, {"estimator_params": cfg["estimator_params"]})


def test_16_stage_boundary_no_pilot_confirm():
    cfg = dp.build_frozen_config()
    dp.assert_no_stage_leak(cfg)  # 不抛异常
    bad = dp.build_frozen_config()
    bad["narrow_scope"]["pilot"] = True
    with pytest.raises(dp.StageBoundaryError):
        dp.assert_no_stage_leak(bad)
    assert cfg["narrow_scope"]["confirm"] is False
    assert cfg["narrow_scope"]["confirmatory_delta_ba"] is False
    assert cfg["narrow_scope"]["bootstrap"] is False
