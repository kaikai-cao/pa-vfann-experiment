"""H1-RM.3A.11 DEV-2: GroupKFold 主模型选择、训练与冻结.

严格边界:
  * 只读取 DEV-1 已经生成的 125-pair 数据; 不重新生成、不修改特征、不追加样本.
  * 只对 C1 / C2 各训练一个主模型; 不训练 C0、不训练 ensemble、不做稳定性种子训练.
  * 不运行 PILOT / CONFIRM, 不计算确认性 ΔBA / bootstrap / 功效.
  * 所有 DEV 数据、pair ID 映射、模型工件、日志写入仓库外私有目录.

冻结实现约定 (操作性, 非协议逐项规定, 见任务包 5.3):
  sklearn LogisticRegression(penalty="l2", solver="lbfgs", fit_intercept=True,
  class_weight=None, tol=1e-8, max_iter=10000, dual=False, warm_start=False,
  n_jobs=None, random_state=None). lbfgs 为确定性求解器, 不依赖随机种子;
  协议主种子字符串仅作为身份标识写入配置, 不传给 sklearn.

用法:
  python dev2_model_freeze.py --dev-root <DEV-1 私有目录> --private-root <DEV-2 私有目录>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import pickle
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# 冻结常量
# ---------------------------------------------------------------------------

STAGE = "H1-RM.3A.11"
MAIN_SEED_IDENTITY = "H1-RM.3A9-MAIN-SEED-20261126"  # 协议身份标识, 非 sklearn random_state
C_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0)
N_SPLITS = 5
EXPECTED_PAIRS = 125
EXPECTED_ROWS_PER_GROUP = 250
EXPECTED_FEATURE_DIM = 117
DECISION_THRESHOLD = 0.5
LABEL_COLUMN = "label"
STRATEGIES: tuple[str, ...] = ("C1", "C2")

# 冻结实现参数 (任务包 5.3); 构建分类器时逐项显式设置.
FROZEN_ESTIMATOR_PARAMS: dict[str, Any] = {
    "penalty": "l2",
    "solver": "lbfgs",
    "fit_intercept": True,
    "class_weight": None,
    "tol": 1e-8,
    "max_iter": 10000,
    "dual": False,
    "warm_start": False,
    "n_jobs": None,
    "random_state": None,
}

DEV1_COLUMNS_SHA256 = "c107d7ef8e7cdf142ad3788b9585d27457c4c8381b817a67090ac05009b08429"


class Dev2Stop(RuntimeError):
    """任一停止条件触发时抛出, 上层立即终止, 不绕过."""


class DataAdmissionError(Dev2Stop):
    """数据准入检查失败."""


class ConfigFrozenError(Dev2Stop):
    """冻结训练配置被改动或无法按冻结值执行."""


class StageBoundaryError(Dev2Stop):
    """阶段边界被突破 (如请求训练 C0 / PILOT / CONFIRM)."""


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def sha256_columns(columns: Sequence[str]) -> str:
    """与 DEV-1 manifest feature_schema.columns_sha256 一致的算法 (canonical JSON)."""
    payload = json.dumps(list(columns), sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def software_environment() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "scipy_version": _scipy_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
    }


def _scipy_version() -> str:
    import scipy
    return scipy.__version__


# ---------------------------------------------------------------------------
# 数据读取与准入检查
# ---------------------------------------------------------------------------

def load_dev1_manifest(dev_root: Path) -> dict[str, Any]:
    manifest_path = Path(dev_root) / "manifest.json"
    if not manifest_path.is_file():
        raise DataAdmissionError(f"DEV-1 manifest 不存在: {manifest_path}")
    manifest = read_json(manifest_path)
    if manifest.get("stage") != "H1-RM.3A.10 DEV-1":
        raise DataAdmissionError("manifest stage 不是 H1-RM.3A.10 DEV-1")
    if manifest.get("summary", {}).get("valid_pairs") != EXPECTED_PAIRS:
        raise DataAdmissionError("DEV-1 manifest 有效 pair 不是 125")
    if manifest.get("summary", {}).get("technical_or_structural_failures") != 0:
        raise DataAdmissionError("DEV-1 manifest 存在技术/结构性失败")
    return manifest


def read_feature_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise DataAdmissionError(f"特征 CSV 为空: {path}")
    return rows[0], rows[1:]


def read_grouping_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise DataAdmissionError(f"分组 CSV 为空: {path}")
    expected_fields = {"row_index", "pair_id", "acl_state", "label"}
    if set(rows[0].keys()) != expected_fields:
        raise DataAdmissionError(f"分组 CSV 字段不符: {path}")
    return rows


def _check_finite_features(header: list[str], body: list[list[str]], path: Path) -> None:
    for r_i, row in enumerate(body):
        if len(row) != len(header):
            raise DataAdmissionError(f"{path.name} 第 {r_i} 行列数不符")
        for c_i, cell in enumerate(row[:-1]):
            cell = cell.strip()
            if cell == "" or cell.lower() in {"nan", "inf", "-inf", "+inf", "none"}:
                raise DataAdmissionError(f"{path.name} 第 {r_i} 行第 {c_i} 列非法值: {cell}")
            try:
                value = float(cell)
            except ValueError as exc:
                raise DataAdmissionError(f"{path.name} 第 {r_i} 行第 {c_i} 列非数值") from exc
            if not math.isfinite(value):
                raise DataAdmissionError(f"{path.name} 第 {r_i} 行第 {c_i} 列 NaN/Inf")


def _validate_one_strategy(
    strategy: str,
    dev_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    feature_path = Path(dev_root) / "features" / f"{strategy}_features.csv"
    grouping_path = Path(dev_root) / "features" / f"{strategy}_grouping_private.csv"
    if not feature_path.is_file() or not grouping_path.is_file():
        raise DataAdmissionError(f"{strategy} 输入文件缺失")

    header, body = read_feature_csv(feature_path)
    grouping = read_grouping_csv(grouping_path)
    feature_sha = sha256_file(feature_path)
    grouping_sha = sha256_file(grouping_path)

    # 特征 schema: 顺序、列名、SHA 必须与 DEV-1 manifest 完全一致.
    frozen_columns: list[str] = manifest["feature_schema"]["columns"]
    if header != frozen_columns:
        raise DataAdmissionError(f"{strategy} 特征列顺序/表头与 DEV-1 manifest 不一致")
    if sha256_columns(header) != DEV1_COLUMNS_SHA256:
        raise DataAdmissionError(f"{strategy} 完整表头 SHA-256 与 DEV-1 不一致")
    if len(header) - 1 != EXPECTED_FEATURE_DIM:
        raise DataAdmissionError(f"{strategy} 特征维度不是 117")
    if any(token in c.lower() for c in header[:-1] for token in ("pair", "acl", "internal", "truth")):
        raise DataAdmissionError(f"{strategy} 特征列含禁止字段")

    if len(body) != EXPECTED_ROWS_PER_GROUP:
        raise DataAdmissionError(f"{strategy} 数据行数不是 250")
    _check_finite_features(header, body, feature_path)

    if len(grouping) != len(body):
        raise DataAdmissionError(f"{strategy} grouping 行数与特征行数不一致")

    row_indices: list[int] = []
    pair_to_rows: dict[str, dict[str, int]] = {}
    pair_to_labels: dict[str, dict[str, str]] = {}
    for g_i, g in enumerate(grouping):
        try:
            r_i = int(g["row_index"])
        except ValueError as exc:
            raise DataAdmissionError(f"{strategy} grouping row_index 非法") from exc
        row_indices.append(r_i)
        pair_id, state, label = g["pair_id"], g["acl_state"], g["label"]
        if state not in ("A0", "A1"):
            raise DataAdmissionError(f"{strategy} grouping acl_state 非法: {state}")
        expected_label = "0" if state == "A0" else "1"
        if label != expected_label:
            raise DataAdmissionError(f"{strategy} grouping 标签与 acl_state 不一致")
        if body[r_i][-1].strip() != label:
            raise DataAdmissionError(f"{strategy} 特征标签与 grouping 不一致 (row {r_i})")
        if pair_id in pair_to_rows and state in pair_to_rows[pair_id]:
            raise DataAdmissionError(f"{strategy} pair {pair_id} 的 {state} 重复")
        pair_to_rows.setdefault(pair_id, {})[state] = r_i
        pair_to_labels.setdefault(pair_id, {})[state] = label

    if sorted(row_indices) != list(range(EXPECTED_ROWS_PER_GROUP)):
        raise DataAdmissionError(f"{strategy} 行索引不唯一或不连续")

    pair_ids = sorted(pair_to_rows)
    if len(pair_ids) != EXPECTED_PAIRS:
        raise DataAdmissionError(f"{strategy} 不同 pair 数不是 125")
    for pair_id in pair_ids:
        if set(pair_to_rows[pair_id]) != {"A0", "A1"}:
            raise DataAdmissionError(f"{strategy} pair {pair_id} 缺少 A0 或 A1")

    labels = [row[-1].strip() for row in body]
    if labels.count("0") != EXPECTED_PAIRS or labels.count("1") != EXPECTED_PAIRS:
        raise DataAdmissionError(f"{strategy} A0/A1 标签数不是各 125")

    return {
        "strategy": strategy,
        "feature_file": str(feature_path),
        "grouping_file": str(grouping_path),
        "feature_sha256": feature_sha,
        "grouping_sha256": grouping_sha,
        "rows": len(body),
        "pair_ids": pair_ids,
        "pair_to_rows": pair_to_rows,
        "header": header,
        "body": body,
        "labels": labels,
        "feature_columns_sha256": sha256_columns(header),
    }


def validate_inputs(dev_root: Path) -> dict[str, Any]:
    """对 C1 / C2 执行完整数据准入检查, 失败立即停止训练."""
    dev_root = Path(dev_root)
    manifest = load_dev1_manifest(dev_root)
    validated: dict[str, Any] = {}
    for strategy in STRATEGIES:
        validated[strategy] = _validate_one_strategy(strategy, dev_root, manifest)

    c1, c2 = validated["C1"], validated["C2"]
    if c1["pair_ids"] != c2["pair_ids"]:
        raise DataAdmissionError("C1 与 C2 的 pair 集合不一致")
    for pair_id in c1["pair_ids"]:
        for state in ("A0", "A1"):
            r1, r2 = c1["pair_to_rows"][pair_id][state], c2["pair_to_rows"][pair_id][state]
            if c1["labels"][r1] != c2["labels"][r2]:
                raise DataAdmissionError(f"C1/C2 分组标签映射不一致: {pair_id}/{state}")
    if c1["header"] != c2["header"]:
        raise DataAdmissionError("C1/C2 特征表头不一致")
    if c1["feature_columns_sha256"] != c2["feature_columns_sha256"]:
        raise DataAdmissionError("C1/C2 特征 schema digest 不一致")

    report: dict[str, Any] = {
        "stage": STAGE,
        "dev1_manifest_sha256": sha256_file(dev_root / "manifest.json"),
        "dev1_manifest_summary": manifest["summary"],
        "feature_schema": manifest["feature_schema"],
        "strategies": {},
        "pair_sets_identical": True,
        "grouping_maps_identical": True,
        "no_visibility_filtering": True,
        "status": "PASS",
    }
    for strategy in STRATEGIES:
        v = validated[strategy]
        report["strategies"][strategy] = {
            k: v[k] for k in (
                "feature_file", "grouping_file", "feature_sha256", "grouping_sha256",
                "rows", "pair_ids", "pair_to_rows", "header", "labels", "feature_columns_sha256",
            )
        }
    return report


def arrays_from_validation(v: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """从准入结果构造 X / y / pair_id 数组 (仅内存, 不落盘).

    从准入时记录的私有文件路径重新读取, 避免把全部特征数据写进 validation JSON.
    """
    header, body = read_feature_csv(Path(v["feature_file"]))
    grouping = v["pair_to_rows"]
    pair_by_row: dict[int, str] = {}
    for pair_id, states in grouping.items():
        for r_i in states.values():
            pair_by_row[r_i] = pair_id
    X = np.asarray([[float(c) for c in row[:-1]] for row in body], dtype=np.float64)
    y = np.asarray([int(row[-1]) for row in body], dtype=np.int64)
    pair_ids = [pair_by_row[i] for i in range(len(body))]
    return X, y, np.asarray(pair_ids), header[:-1]


# ---------------------------------------------------------------------------
# 冻结配置
# ---------------------------------------------------------------------------

def build_frozen_config() -> dict[str, Any]:
    """构造完整冻结训练配置; 第一次拟合前写入私有目录, 之后不得改动."""
    return {
        "stage": STAGE,
        "model": "LogisticRegression",
        "task": "binary",
        "input_dim": EXPECTED_FEATURE_DIM,
        "decision_threshold": DECISION_THRESHOLD,
        "class_weight": None,
        "sample_weights": False,
        "class_balancing": False,
        "ensemble": False,
        "C_grid": list(C_GRID),
        "estimator_params": dict(FROZEN_ESTIMATOR_PARAMS),
        "main_seed_identity": MAIN_SEED_IDENTITY,
        "sklearn_random_state": None,
        "random_state_note": (
            "lbfgs 是确定性求解器, 不依赖随机种子; 协议主种子字符串仅作身份标识, "
            "不传给 sklearn. 本组实现参数是 DEV 阶段操作性约定, 非协议逐项规定, "
            "不得在看到结果后更换 solver / tol / max_iter."
        ),
        "standardization": {
            "estimator": "StandardScaler",
            "cv": "fit_on_training_fold_only",
            "final": "refit_on_full_dev",
        },
        "cv": {
            "splitter": "GroupKFold",
            "n_splits": N_SPLITS,
            "groups": "private_pair_id",
            "scoring": "balanced_accuracy",
            "selection": "max_mean_validation_ba",
            "tie_break": "smaller_C",
        },
        "narrow_scope": {
            "c0_main_model": False,
            "stability_seed_training": False,
            "pilot": False,
            "confirm": False,
            "confirmatory_delta_ba": False,
            "bootstrap": False,
            "power": False,
        },
    }


def _config_digest(config: dict[str, Any]) -> str:
    """配置 SHA 在排除自指字段 config_sha256 后计算."""
    payload = {k: v for k, v in config.items() if k != "config_sha256"}
    return sha256_json(payload)


def freeze_config(private_root: Path) -> tuple[dict[str, Any], str]:
    """写入并冻结训练配置; 若已存在则必须逐字节一致, 否则视为配置被事后覆盖."""
    private_root = Path(private_root)
    path = private_root / "frozen_training_config.json"
    config = build_frozen_config()
    config["software_environment"] = software_environment()
    config_sha = _config_digest(config)
    config["config_sha256"] = config_sha
    if path.exists():
        existing = read_json(path)
        if existing.get("config_sha256") != config_sha or existing != config:
            raise ConfigFrozenError("frozen_training_config.json 已存在但内容不一致 (疑似运行时覆盖)")
        return existing, config_sha
    write_json(path, config)
    if _config_digest(read_json(path)) != config_sha:
        raise ConfigFrozenError("写入后的配置 SHA 校验失败")
    return config, config_sha


def load_frozen_config(private_root: Path, expected_sha: str) -> dict[str, Any]:
    """训练前复核配置未被运行时覆盖."""
    path = Path(private_root) / "frozen_training_config.json"
    if not path.is_file():
        raise ConfigFrozenError("冻结训练配置不存在")
    config = read_json(path)
    if _config_digest(config) != expected_sha:
        raise ConfigFrozenError("冻结训练配置 SHA 与训练开始时不一致")
    return config


def make_estimator(C: float, config: dict[str, Any] | None = None) -> LogisticRegression:
    """按冻结参数构造分类器; 不接受运行时覆盖."""
    params = dict(FROZEN_ESTIMATOR_PARAMS)
    params["C"] = float(C)
    if config is not None:
        frozen_params = config.get("estimator_params")
        if frozen_params != FROZEN_ESTIMATOR_PARAMS:
            raise ConfigFrozenError("传入配置的 estimator_params 与冻结值不符")
    return LogisticRegression(**params)


# ---------------------------------------------------------------------------
# GroupKFold 折划分
# ---------------------------------------------------------------------------

def build_folds(pair_ids: Sequence[str]) -> list[dict[str, Any]]:
    """用私有 pair ID 作为 group 构造 5 折; 断言 A0/A1 同折与 25/100 pair."""
    unique_pairs = sorted(set(pair_ids))
    if len(unique_pairs) != EXPECTED_PAIRS:
        raise DataAdmissionError("pair 数不是 125, 拒绝构造 GroupKFold")
    row_pair_index = np.asarray([unique_pairs.index(p) for p in pair_ids], dtype=np.int64)
    X_dummy = np.zeros((len(pair_ids), 1), dtype=np.float64)
    splitter = GroupKFold(n_splits=N_SPLITS)
    folds: list[dict[str, Any]] = []
    for fold_i, (train_idx, val_idx) in enumerate(
        splitter.split(X_dummy, groups=row_pair_index)
    ):
        train_pairs = sorted({pair_ids[i] for i in train_idx})
        val_pairs = sorted({pair_ids[i] for i in val_idx})
        if len(val_pairs) != EXPECTED_PAIRS // N_SPLITS:
            raise DataAdmissionError(f"fold {fold_i} 验证 pair 不是 25")
        if len(train_pairs) != EXPECTED_PAIRS - EXPECTED_PAIRS // N_SPLITS:
            raise DataAdmissionError(f"fold {fold_i} 训练 pair 不是 100")
        if len(val_idx) != 2 * len(val_pairs) or len(train_idx) != 2 * len(train_pairs):
            raise DataAdmissionError(f"fold {fold_i} A0/A1 未成对进入同一集合")
        for pair_id in val_pairs:
            pair_rows = [i for i in val_idx if pair_ids[i] == pair_id]
            if len(pair_rows) != 2:
                raise DataAdmissionError(f"fold {fold_i} pair {pair_id} 被拆分")
        folds.append({
            "fold": fold_i,
            "train_row_indices": [int(i) for i in train_idx],
            "val_row_indices": [int(i) for i in val_idx],
            "train_pair_ids": train_pairs,
            "val_pair_ids": val_pairs,
            "train_pairs": len(train_pairs),
            "val_pairs": len(val_pairs),
            "train_rows": len(train_idx),
            "val_rows": len(val_idx),
        })
    return folds


# ---------------------------------------------------------------------------
# CV 与 C 选择
# ---------------------------------------------------------------------------

def cv_fold_metrics(
    X: np.ndarray,
    y: np.ndarray,
    train_idx: Sequence[int],
    val_idx: Sequence[int],
    C: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """单折: 仅训练折拟合 scaler; 训练折拟合分类器; 验证折计算 BA.

    返回 scaler 的 mean_/scale_ 摘要与拟合行索引 SHA, 供测试验证拟合范围.
    """
    clf = make_estimator(C, config)
    scaler = StandardScaler()
    train_idx = np.asarray(list(train_idx), dtype=np.int64)
    val_idx = np.asarray(list(val_idx), dtype=np.int64)
    X_train = scaler.fit_transform(X[train_idx])
    X_val = scaler.transform(X[val_idx])
    clf.fit(X_train, y[train_idx])
    proba = clf.predict_proba(X_val)[:, 1]
    pred = (proba >= DECISION_THRESHOLD).astype(np.int64)
    ba = float(balanced_accuracy_score(y[val_idx], pred))
    cm = confusion_matrix(y[val_idx], pred, labels=[0, 1])
    n_iter = int(np.max(np.asarray(clf.n_iter_)))
    return {
        "C": C,
        "ba": ba,
        "confusion_matrix": cm.tolist(),
        "converged": n_iter < FROZEN_ESTIMATOR_PARAMS["max_iter"],
        "n_iter": n_iter,
        "train_rows": int(len(train_idx)),
        "val_rows": int(len(val_idx)),
        "scaler_fit_row_indices_sha256": sha256_bytes(
            np.asarray(sorted(train_idx.tolist())).tobytes()
        ),
        "scaler_mean_first3": [float(v) for v in scaler.mean_[:3]],
        "scaler_scale_first3": [float(v) for v in scaler.scale_[:3]],
        "scaler_fitted_on_all_rows": bool(
            sha256_bytes(np.asarray(sorted(train_idx.tolist())).tobytes())
            == sha256_bytes(np.arange(len(X), dtype=np.int64).tobytes())
        ),
    }


def run_cv(
    X: np.ndarray,
    y: np.ndarray,
    pair_ids: Sequence[str],
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """C1 / C2 各自的 5×5 CV; 只用于 DEV 内部选择 C, 不是确认性统计结果."""
    folds = build_folds(pair_ids)
    cv_results: dict[str, Any] = {
        "stage": STAGE,
        "note": "DEV 内部超参数选择; 五折不是五个独立实验, 不得用于显著性/置信区间.",
        "n_splits": N_SPLITS,
        "folds": folds,
        "by_C": {},
    }
    for C in C_GRID:
        fold_metrics = []
        for fold in folds:
            metrics = cv_fold_metrics(
                X, y, fold["train_row_indices"], fold["val_row_indices"], C, config
            )
            metrics["fold"] = fold["fold"]
            metrics["val_pair_ids"] = fold["val_pair_ids"]
            fold_metrics.append(metrics)
        mean_ba = float(np.mean([m["ba"] for m in fold_metrics]))
        cv_results["by_C"][str(C)] = {
            "C": C,
            "mean_ba": mean_ba,
            "folds": fold_metrics,
        }
    return cv_results, folds


def select_c(cv_results: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """平均 BA 最高者; 完全相同则取更小的 C (禁止按单折挑选)."""
    # key = (mean_ba, -C): 均值相同时 -C 较大者 (即 C 较小者) 胜出.
    best_key, chosen = max(
        (
            (entry["mean_ba"], -entry["C"]),
            entry["C"],
        )
        for entry in cv_results["by_C"].values()
    )
    return float(chosen), cv_results["by_C"][str(chosen)]


# ---------------------------------------------------------------------------
# 最终主模型训练、保存、加载
# ---------------------------------------------------------------------------

def train_final_model(
    X: np.ndarray,
    y: np.ndarray,
    C: float,
    config: dict[str, Any],
) -> tuple[StandardScaler, LogisticRegression, dict[str, Any]]:
    """在完整 DEV 数据上重新拟合 scaler + 分类器."""
    clf = make_estimator(C, config)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    clf.fit(X_scaled, y)
    n_iter = int(np.max(np.asarray(clf.n_iter_)))
    info = {
        "C": C,
        "n_iter": n_iter,
        "converged": n_iter < FROZEN_ESTIMATOR_PARAMS["max_iter"],
        "train_rows": int(len(y)),
        "train_pairs": EXPECTED_PAIRS,
        "scaler_refit_on_full_dev": True,
        "scaler_mean_first3": [float(v) for v in scaler.mean_[:3]],
        "scaler_scale_first3": [float(v) for v in scaler.scale_[:3]],
    }
    if not info["converged"]:
        raise Dev2Stop("最终模型未收敛 (n_iter 达到 max_iter), 停止并报告")
    return scaler, clf, info


def fixed_probe_inputs() -> np.ndarray:
    """确定性固定测试输入 (合成向量, 非 DEV 数据, 不含 pair ID)."""
    rng = np.random.default_rng(20261126)
    return rng.normal(loc=0.0, scale=1.7, size=(4, EXPECTED_FEATURE_DIM))


def predict_with(
    scaler: StandardScaler,
    clf: LogisticRegression,
    X_probe: np.ndarray,
) -> dict[str, Any]:
    X_scaled = scaler.transform(X_probe)
    proba = clf.predict_proba(X_scaled)[:, 1]
    pred = (proba >= DECISION_THRESHOLD).astype(int).tolist()
    return {
        "probe_sha256": sha256_bytes(X_probe.astype(np.float64).tobytes()),
        "threshold": DECISION_THRESHOLD,
        "probabilities": [float(v) for v in proba],
        "predictions": pred,
    }


def save_model_artifact(
    model_dir: Path,
    scaler: StandardScaler,
    clf: LogisticRegression,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """保存 scaler + 分类器 + 元数据; 模型工件不含 DEV 数据或 pair ID 映射."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = model_dir / "model.pkl"
    # metadata 内嵌 artifact digest 会形成自指, 故工件只保存参数; digest 单独写入 metadata.
    artifact_payload = {"scaler": scaler, "classifier": clf}
    with artifact_path.open("wb") as fh:
        pickle.dump(artifact_payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    artifact_sha = sha256_file(artifact_path)
    metadata["model_artifact_sha256"] = artifact_sha
    write_json(model_dir / "model_metadata.json", metadata)
    return {
        "artifact_path": str(artifact_path),
        "artifact_sha256": artifact_sha,
        "metadata_sha256": sha256_file(model_dir / "model_metadata.json"),
    }


def load_model_artifact(model_dir: Path) -> tuple[StandardScaler, LogisticRegression, dict[str, Any]]:
    model_dir = Path(model_dir)
    artifact_path = model_dir / "model.pkl"
    with artifact_path.open("rb") as fh:
        obj = pickle.load(fh)
    metadata = read_json(model_dir / "model_metadata.json")
    if metadata.get("model_artifact_sha256") != sha256_file(artifact_path):
        raise Dev2Stop("模型工件 digest 与元数据不一致")
    return obj["scaler"], obj["classifier"], metadata


def assert_no_stage_leak(config: dict[str, Any]) -> None:
    narrow = config.get("narrow_scope", {})
    for key in ("pilot", "confirm", "confirmatory_delta_ba", "bootstrap", "power",
                "c0_main_model", "stability_seed_training"):
        if narrow.get(key) is not False:
            raise StageBoundaryError(f"阶段边界配置被改动: {key}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_dev2(dev_root: Path, private_root: Path) -> dict[str, Any]:
    dev_root, private_root = Path(dev_root), Path(private_root)
    private_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    log_lines: list[str] = []

    def log(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {msg}"
        log_lines.append(line)

    try:
        log(f"stage={STAGE} dev_root={dev_root} private_root={private_root}")
        # 1) 配置冻结 (第一次拟合之前)
        config, config_sha = freeze_config(private_root)
        assert_no_stage_leak(config)
        log(f"frozen_training_config sha256={config_sha}")

        # 2) 数据准入
        validation = validate_inputs(dev_root)
        write_json(private_root / "input_validation.json", validation)
        log("input validation PASS (125 pairs / 250 rows per strategy)")

        # 3) 拟合前再次核验配置未被运行时覆盖
        load_frozen_config(private_root, config_sha)
        log("config re-verified before first model fit")

        # 4) C1 / C2 各自的 CV 与 C 选择
        selected: dict[str, Any] = {}
        cv_reports: dict[str, Any] = {}
        final_models: dict[str, Any] = {}
        for strategy in STRATEGIES:
            v = validation["strategies"][strategy]
            X, y, pair_ids, feature_names = arrays_from_validation(v)
            cv_results, folds = run_cv(X, y, pair_ids, config)
            cv_path = private_root / f"{strategy}_cv_results.json"
            write_json(cv_path, cv_results)
            C, chosen_entry = select_c(cv_results)
            log(f"{strategy} CV done, selected C={C}, mean_ba={chosen_entry['mean_ba']:.6f}")
            cv_reports[strategy] = {
                "cv_file": str(cv_path),
                "cv_sha256": sha256_file(cv_path),
                "selected_C": C,
                "mean_ba_by_C": {c: e["mean_ba"] for c, e in cv_results["by_C"].items()},
                "selection_rule": "max_mean_validation_ba; tie -> smaller_C",
                "selection_entry_sha256": sha256_json(chosen_entry),
            }

            # 4) 最终主模型 (完整 DEV 重新拟合 scaler)
            scaler, clf, final_info = train_final_model(X, y, C, config)
            probe = fixed_probe_inputs()
            pre_predict = predict_with(scaler, clf, probe)
            metadata = {
                "stage": STAGE,
                "strategy": strategy,
                "model": "LogisticRegression",
                "selected_C": C,
                "frozen_estimator_params": dict(FROZEN_ESTIMATOR_PARAMS),
                "config_sha256": config_sha,
                "feature_names": feature_names,
                "feature_dim": EXPECTED_FEATURE_DIM,
                "feature_columns_sha256": v["feature_columns_sha256"],
                "dev1_manifest_sha256": validation["dev1_manifest_sha256"],
                "training_data_sha256": v["feature_sha256"],
                "grouping_file_sha256": v["grouping_sha256"],
                "software_environment": software_environment(),
                "final_training": final_info,
                "scaler_parameters": {
                    "mean": [float(x) for x in scaler.mean_],
                    "scale": [float(x) for x in scaler.scale_],
                    "var": [float(x) for x in scaler.var_],
                    "n_features_in": int(scaler.n_features_in_),
                },
                "classifier_parameters": {
                    "coef": [float(x) for x in clf.coef_[0]],
                    "intercept": [float(x) for x in clf.intercept_],
                    "classes": [int(x) for x in clf.classes_],
                    "n_features_in": int(clf.n_features_in_),
                },
                "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "contains_dev_data_or_pair_ids": False,
            }
            artifact_info = save_model_artifact(
                private_root / f"{strategy}_model", scaler, clf, metadata
            )

            # 5) 独立加载 + 固定测试输入预测一致性
            loaded_scaler, loaded_clf, loaded_meta = load_model_artifact(
                private_root / f"{strategy}_model"
            )
            post_predict = predict_with(loaded_scaler, loaded_clf, probe)
            if post_predict != pre_predict:
                raise Dev2Stop(f"{strategy} 模型加载后预测结果与保存前不一致")
            if loaded_meta["model_artifact_sha256"] != artifact_info["artifact_sha256"]:
                raise Dev2Stop(f"{strategy} 加载后元数据 artifact digest 不一致")
            load_check = {
                "strategy": strategy,
                "pre_save": pre_predict,
                "post_load": post_predict,
                "identical": True,
                "artifact_sha256": artifact_info["artifact_sha256"],
            }
            write_json(private_root / f"{strategy}_load_and_predict_check.json", load_check)
            log(f"{strategy} model frozen, artifact sha256={artifact_info['artifact_sha256']}")

            selected[strategy] = {
                "selected_C": C,
                "selected_mean_ba": chosen_entry["mean_ba"],
                "cv": cv_reports[strategy],
                "final_training": final_info,
                "model_dir": str(private_root / f"{strategy}_model"),
                "artifact_sha256": artifact_info["artifact_sha256"],
                "load_and_predict_identical": True,
            }
            final_models[strategy] = {
                "feature_names": feature_names,
                "scaler": scaler,
                "clf": clf,
            }

        # 6) 冻结 manifest (含每折 pair ID 私有映射)
        fold_map: dict[str, Any] = {}
        for strategy in STRATEGIES:
            v = validation["strategies"][strategy]
            _, _, pair_ids, _ = arrays_from_validation(v)
            fold_map[strategy] = build_folds(pair_ids)
        manifest = {
            "stage": STAGE,
            "status": "DEV2_READY_MODEL_FROZEN",
            "dev1_manifest_sha256": validation["dev1_manifest_sha256"],
            "input_validation_sha256": sha256_file(private_root / "input_validation.json"),
            "input_files": {
                s: {
                    "features_sha256": validation["strategies"][s]["feature_sha256"],
                    "grouping_sha256": validation["strategies"][s]["grouping_sha256"],
                } for s in STRATEGIES
            },
            "feature_schema": validation["feature_schema"],
            "feature_columns": validation["strategies"]["C1"]["header"][:-1],
            "groupkfold_folds_private": fold_map,
            "selection": selected,
            "frozen_training_config": config,
            "config_sha256": config_sha,
            "software_environment": software_environment(),
            "stage_boundary": {
                "pilot_run": False, "confirm_run": False,
                "confirmatory_delta_ba": False, "bootstrap": False, "power": False,
                "c0_model_trained": False, "stability_training": False,
                "ensemble": False, "dev_data_regenerated": False, "features_modified": False,
            },
            "model_freeze_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "training_status": "SUCCESS",
            "elapsed_seconds": round(time.time() - started, 3),
        }
        write_json(private_root / "model_freeze_manifest.json", manifest)
        manifest_sha = sha256_file(private_root / "model_freeze_manifest.json")
        log(f"model_freeze_manifest sha256={manifest_sha}")
        return {
            "status": "DEV2_READY_MODEL_FROZEN",
            "selected_C": {s: selected[s]["selected_C"] for s in STRATEGIES},
            "mean_ba_by_C": cv_reports,
            "artifact_sha256": {s: selected[s]["artifact_sha256"] for s in STRATEGIES},
            "model_freeze_manifest_sha256": manifest_sha,
        }
    except Dev2Stop as exc:
        log(f"STOP: {exc}")
        write_json(private_root / "dev2_failure.json", {"error": str(exc), "logs": log_lines})
        raise
    finally:
        (private_root / "run_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-root", required=True, help="DEV-1 私有数据目录")
    parser.add_argument("--private-root", required=True, help="DEV-2 私有产物目录")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_dev2(Path(args.dev_root), Path(args.private_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
