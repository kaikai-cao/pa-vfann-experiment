"""H1-RM.3A.12 — Independent PILOT: frozen-model pair-level variance estimation.

Scope (strict):
  * Generate exactly 51 NEW independent ACL pairs in a distinct PILOT namespace.
  * Reuse DEV-1 frozen atomic primitives BY IMPORT (never copy/modify their logic).
  * Load the DEV-2 frozen C1/C2 artifacts; verify every digest and config SHA;
    NEVER refit scaler or classifier, never change threshold (fixed 0.5).
  * Compute one d_i = s_C2,i - s_C1,i per pair with s_Cj,i=(I_A0+I_A1)/2.
  * Estimate sigma_d^2 with sample variance (ddof=1) and N_confirm by the
    frozen protocol formula. NO H1 test, NO confirmatory CI, NO model changes.

All private artifacts go to a caller-supplied directory OUTSIDE the repository.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Frozen constants (mirror DEV-1 / DEV-2; never a source of new design)
# --------------------------------------------------------------------------- #

STAGE = "H1-RM.3A.12"
PILOT_NAMESPACE = "PILOT"
PILOT_PAIRS = 51
TARGET_INDEX = 103
TARGET_LABEL = 101751
DECISION_THRESHOLD = 0.5
CONFIRM_COEFF = 618.26
CONFIRM_FLOOR = 30

# DEV-2 frozen manifest digests (recorded at freeze time; verified at load).
EXPECTED_DEV2_MANIFEST_SHA = "8e8610e6389615a3947c98d8251ce37f435b3c4d7e9014401a28064e048831da"
EXPECTED_DEV2_CONFIG_SHA = "58948b090b49de91262a0d69fc6a6c45f25ef77b3e79319488daa691a2ad3066"
EXPECTED_ARTIFACT_SHA = {
    "C1": "ef12c981cbabd0a02b8e6c6bf59cefdb76e7528d13b65fcc3865294298832674",
    "C2": "9e0fabbd4c5e6ce6367a09ded759567c127d252b533522c09e7a02b17c08d66f",
}
EXPECTED_SELECTED_C = {"C1": 0.01, "C2": 10.0}
DEV1_COLUMNS_SHA256 = "c107d7ef8e7cdf142ad3788b9585d27457c4c8381b817a67090ac05009b08429"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV1_MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a10_dev1_data_pipeline" / "dev1_pipeline.py"
DEV2_MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a11_dev2_model_freeze" / "dev2_model_freeze.py"

DEV1_PRIVATE_DEFAULT = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
DEV2_PRIVATE_DEFAULT = Path(r"D:/Research/pa-vfann-h1-rm3a11-dev2-private-v1")


class PilotStop(RuntimeError):
    """Any stop condition; caller halts immediately, no repair, no resample."""


class FrozenArtifactError(PilotStop):
    """A frozen artifact digest / config SHA / schema check failed."""


class FrozenFitAttempt(PilotStop):
    """A fit-like method was invoked on a frozen model wrapper."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise PilotStop(f"cannot load module {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_columns(columns: Sequence[str]) -> str:
    import hashlib
    return hashlib.sha256(
        json.dumps(list(columns), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_private_root(private_root: Path) -> Path:
    """Refuse any private artifact location inside the repository."""
    root = Path(private_root).resolve()
    repo = REPO_ROOT.resolve()
    if root == repo or repo in root.parents:
        raise PilotStop("private_root must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------- #
# Frozen-model read-only wrapper (never exposes fit / fit_transform / partial_fit)
# --------------------------------------------------------------------------- #

class FrozenPredictor:
    """Read-only view of a DEV-2 frozen (scaler, classifier).

    Only transform+thresholded predict_proba is exposed. There is deliberately
    no ``fit``, ``fit_transform``, ``partial_fit`` attribute so any attempt to
    refit is impossible by construction (and would raise AttributeError).
    """

    __slots__ = ("_scaler", "_clf", "_feature_names", "_strategy", "_selected_C")

    def __init__(self, scaler: Any, clf: Any, feature_names: list[str],
                 strategy: str, selected_C: float) -> None:
        self._scaler = scaler
        self._clf = clf
        self._feature_names = list(feature_names)
        self._strategy = strategy
        self._selected_C = float(selected_C)

    @property
    def feature_names(self) -> list[str]:
        return list(self._feature_names)

    @property
    def selected_C(self) -> float:
        return self._selected_C

    def predict_labels(self, X: np.ndarray) -> np.ndarray:
        """Standardize with the FROZEN scaler, threshold FROZEN classifier at 0.5."""
        Xs = self._scaler.transform(X)  # transform only; never fit
        proba = self._clf.predict_proba(Xs)[:, 1]
        return (proba >= DECISION_THRESHOLD).astype(int)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("fit", "fit_transform", "partial_fit"):
            raise FrozenFitAttempt("cannot attach a fit method to a frozen model")
        object.__setattr__(self, name, value)


# --------------------------------------------------------------------------- #
# Frozen artifact verification (no refit, no model change)
# --------------------------------------------------------------------------- #

def verify_frozen_artifacts(
    dev1_root: Path,
    dev2_root: Path,
    dev2: Any,
) -> dict[str, Any]:
    """Verify every digest / config SHA / schema before any prediction."""
    dev1_root, dev2_root = Path(dev1_root), Path(dev2_root)
    checks: dict[str, Any] = {}

    manifest_path = dev2_root / "model_freeze_manifest.json"
    if not manifest_path.is_file():
        raise FrozenArtifactError("DEV-2 model_freeze_manifest.json missing")
    manifest_sha = _sha256_file(manifest_path)
    checks["dev2_manifest_sha256"] = manifest_sha
    if manifest_sha != EXPECTED_DEV2_MANIFEST_SHA:
        raise FrozenArtifactError(
            f"DEV-2 manifest SHA mismatch: {manifest_sha} != {EXPECTED_DEV2_MANIFEST_SHA}"
        )

    manifest = _read_json(manifest_path)
    # Config SHA: use DEV-2's own digest algorithm (excludes self-referential field).
    config_path = dev2_root / "frozen_training_config.json"
    if not config_path.is_file():
        raise FrozenArtifactError("frozen_training_config.json missing")
    config = _read_json(config_path)
    config_digest = dev2._config_digest(config)
    checks["config_sha256_recomputed"] = config_digest
    checks["config_sha256_manifest"] = manifest.get("config_sha256")
    if config_digest != EXPECTED_DEV2_CONFIG_SHA or manifest.get("config_sha256") != EXPECTED_DEV2_CONFIG_SHA:
        raise FrozenArtifactError("frozen config SHA mismatch")
    dev2.assert_no_stage_leak(config)

    # DEV-1 input data + schema digest recorded in the frozen manifest.
    dev1_manifest_path = dev1_root / "manifest.json"
    if not dev1_manifest_path.is_file():
        raise FrozenArtifactError("DEV-1 manifest.json missing")
    dev1_manifest_sha = _sha256_file(dev1_manifest_path)
    checks["dev1_manifest_sha256"] = dev1_manifest_sha
    if dev1_manifest_sha != manifest.get("dev1_manifest_sha256"):
        raise FrozenArtifactError("DEV-1 manifest digest does not match frozen manifest")
    dev1_manifest = _read_json(dev1_manifest_path)
    if dev1_manifest.get("feature_schema", {}).get("columns_sha256") != DEV1_COLUMNS_SHA256:
        raise FrozenArtifactError("DEV-1 feature schema digest drifted")

    for strategy in ("C1", "C2"):
        art = dev2_root / strategy / "model.pkl" if (dev2_root / strategy / "model.pkl").is_file() \
            else dev2_root / f"{strategy}_model" / "model.pkl"
        if not art.is_file():
            raise FrozenArtifactError(f"{strategy} model artifact missing")
        art_sha = _sha256_file(art)
        checks[f"{strategy}_artifact_sha256"] = art_sha
        if art_sha != EXPECTED_ARTIFACT_SHA[strategy]:
            raise FrozenArtifactError(f"{strategy} artifact SHA mismatch: {art_sha}")
        if art_sha != manifest["selection"][strategy]["artifact_sha256"]:
            raise FrozenArtifactError(f"{strategy} artifact SHA disagrees with manifest")
        if manifest["selection"][strategy]["selected_C"] != EXPECTED_SELECTED_C[strategy]:
            raise FrozenArtifactError(f"{strategy} selected C drifted")

    checks["feature_schema_columns_sha256"] = DEV1_COLUMNS_SHA256
    checks["status"] = "PASS"
    return checks


def load_frozen_predictors(
    dev2_root: Path,
    dev2: Any,
    feature_columns: list[str],
) -> tuple[dict[str, FrozenPredictor], dict[str, Any]]:
    """Load frozen scaler+classifier into read-only wrappers, no fit anywhere."""
    predictors: dict[str, FrozenPredictor] = {}
    meta_check: dict[str, Any] = {}
    for strategy in ("C1", "C2"):
        model_dir = Path(dev2_root) / f"{strategy}_model"
        scaler, clf, metadata = dev2.load_model_artifact(model_dir)
        if metadata.get("feature_names") != list(feature_columns):
            raise FrozenArtifactError(f"{strategy} model feature names/order mismatch")
        if metadata.get("model_artifact_sha256") != EXPECTED_ARTIFACT_SHA[strategy]:
            raise FrozenArtifactError(f"{strategy} metadata artifact digest mismatch")
        predictors[strategy] = FrozenPredictor(
            scaler, clf, metadata["feature_names"], strategy,
            metadata["selected_C"],
        )
        meta_check[strategy] = {
            "artifact_sha256": metadata["model_artifact_sha256"],
            "n_features": len(metadata["feature_names"]),
            "selected_C": metadata["selected_C"],
            "feature_names_identical": metadata["feature_names"] == list(feature_columns),
        }
    return predictors, meta_check


# --------------------------------------------------------------------------- #
# Statistics (pure functions, unit-testable)
# --------------------------------------------------------------------------- #

def pair_score(correct_a0: int, correct_a1: int) -> float:
    """s_Cj,i = (I_A0 + I_A1)/2."""
    if correct_a0 not in (0, 1) or correct_a1 not in (0, 1):
        raise PilotStop("correct indicators must be 0/1")
    return (int(correct_a0) + int(correct_a1)) / 2.0


def pair_difference(s_c1: float, s_c2: float) -> float:
    """d_i = s_C2,i - s_C1,i."""
    return float(s_c2) - float(s_c1)


def estimate_variance_sq(differences: Sequence[float]) -> float:
    """sigma_d^2 sample variance with ddof=1."""
    arr = np.asarray(list(differences), dtype=np.float64)
    if arr.ndim != 1 or arr.size < 2:
        raise PilotStop("variance requires >=2 differences")
    if not np.all(np.isfinite(arr)):
        raise PilotStop("non-finite difference")
    return float(np.var(arr, ddof=1))


def confirm_sample_size(variance_sq: float) -> int:
    """N_confirm = ceil(max(618.26 * sigma_d^2, 30)); never truncates."""
    if variance_sq < 0 or not math.isfinite(variance_sq):
        raise PilotStop("invalid variance")
    return int(math.ceil(max(CONFIRM_COEFF * variance_sq, CONFIRM_FLOOR)))


def compute_pair_scores_from_features(
    X: np.ndarray,
    y: np.ndarray,
    predictors: dict[str, FrozenPredictor],
) -> dict[str, Any]:
    """Predict with frozen models on aligned A0/A1 rows; return s and d per pair."""
    if X.shape[0] % 2 != 0 or y.shape[0] != X.shape[0]:
        raise PilotStop("features/labels not paired A0/A1 rows")
    scores: dict[str, list[float]] = {"C1": [], "C2": []}
    for i in range(0, X.shape[0], 2):
        if int(y[i]) != 0 or int(y[i + 1]) != 1:
            raise PilotStop("row pair labels are not A0=0/A1=1")
        for strategy in ("C1", "C2"):
            pred = predictors[strategy].predict_labels(X[i:i + 2])
            c_a0 = int(pred[0] == int(y[i]))
            c_a1 = int(pred[1] == int(y[i + 1]))
            scores[strategy].append(pair_score(c_a0, c_a1))
    diffs = [
        pair_difference(s1, s2)
        for s1, s2 in zip(scores["C1"], scores["C2"])
    ]
    return {"s_C1": scores["C1"], "s_C2": scores["C2"], "d_i": diffs}


# --------------------------------------------------------------------------- #
# PILOT data generation — reuse DEV-1 atomic functions by import
# --------------------------------------------------------------------------- #

def _import_dev1() -> Any:
    return _load_module("dev1_pilot_reuse", DEV1_MODULE_PATH)


def generate_pilot_pairs(
    private_root: Path,
    dev1: Any,
    target_pairs: int = PILOT_PAIRS,
) -> dict[str, Any]:
    """Generate 51 independent PILOT pairs using DEV-1 frozen primitives."""
    private = _assert_private_root(private_root)
    constants = dev1.validate_frozen_constants()
    if constants["target"] != TARGET_INDEX or constants["target_label"] != TARGET_LABEL:
        raise PilotStop("frozen target drifted from u=103/label=101751")

    work = private / "work"
    runs_root = private / "runs"
    features_dir = private / "features"
    for d in (work, runs_root, features_dir):
        d.mkdir(parents=True, exist_ok=True)
    harness, loader, compiler_version = dev1.compile_tools(work)

    feature_headers = list(dev1.FEATURE_COLUMNS) + [dev1.LABEL_COLUMN]
    writers: dict[str, Any] = {}
    group_writers: dict[str, Any] = {}
    feature_files: dict[str, Path] = {}
    grouping_files: dict[str, Path] = {}
    for group in ("C1", "C2"):  # C0 kept only as control; not generated as model input
        feature_files[group] = features_dir / f"pilot_{group}_features.csv"
        grouping_files[group] = features_dir / f"pilot_{group}_grouping_private.csv"
        writers[group] = feature_files[group].open("w", newline="", encoding="utf-8")
        group_writers[group] = grouping_files[group].open("w", newline="", encoding="utf-8")
        csv.writer(writers[group]).writerow(feature_headers)
        csv.writer(group_writers[group]).writerow(
            ["row_index", "pair_id", "acl_state", "label"]
        )

    pairs_summary: list[dict[str, Any]] = []
    invisible_pairs: list[str] = []
    valid = 0
    attempt = 0
    started = time.time()
    try:
        while valid < target_pairs:
            attempt += 1
            pair_id = f"{PILOT_NAMESPACE}-{attempt:06d}"
            pair_dir = runs_root / pair_id
            try:
                pair = dev1.build_dev_pair(pair_dir, pair_id)
                structure, observer_events = dev1.run_one_pair(
                    pair, harness, loader, runs_root
                )
                bundle_rows: dict[str, list[dict[str, Any]]] = {g: [] for g in ("C1", "C2")}
                for group in ("C1", "C2"):
                    for state in dev1.ACL_STATES:
                        bundle = dev1.extract_bundle_features(
                            observer_events[group][state], dev1.TARGET_LABEL
                        )
                        dev1.validate_feature_row(bundle)
                        bundle_rows[group].append(bundle)

                for group in ("C1", "C2"):
                    for state, row in zip(dev1.ACL_STATES, bundle_rows[group]):
                        row_index = valid * 2 + dev1.ACL_STATES.index(state)
                        csv.writer(writers[group]).writerow([
                            dev1.LABEL_MAP[state] if c == dev1.LABEL_COLUMN else row[c]
                            for c in feature_headers
                        ])
                        csv.writer(group_writers[group]).writerow(
                            [row_index, pair_id, state, dev1.LABEL_MAP[state]]
                        )

                # Target visibility is recorded but NEVER used to filter pairs.
                vis = structure["target_visibility"]
                any_visible = any(
                    vis[g][s]["observer_visible"] for g in ("C1", "C2") for s in ("A0", "A1")
                )
                pairs_summary.append({
                    "pair_id": pair_id,
                    "base_acl_sha256": pair.safe_summary()["base_acl_sha256"],
                    "a0_blob_sha256": pair.safe_summary()["a0_blob_sha256"],
                    "a1_blob_sha256": pair.safe_summary()["a1_blob_sha256"],
                    "invariant": pair.invariant(),
                    "target_observer_visible": any_visible,
                })
                if not any_visible:
                    invisible_pairs.append(pair_id)
                valid += 1
            except (dev1.StructuralPairFailure, dev1.TechnicalPairFailure) as exc:
                fail = runs_root / pair_id / "failure.json"
                fail.parent.mkdir(parents=True, exist_ok=True)
                _write_json(fail, {"pair_id": pair_id, "stage": type(exc).__name__,
                                   "reason": str(exc), "timestamp": time.time()})
                raise PilotStop(f"PILOT pair {pair_id} structural/technical failure: {exc}")

        finished = time.time()
        return {
            "namespace": PILOT_NAMESPACE,
            "target_pairs": target_pairs,
            "valid_pairs": valid,
            "attempts": attempt,
            "invisible_pairs_kept": invisible_pairs,
            "pairs": pairs_summary,
            "feature_files": {g: str(p) for g, p in feature_files.items()},
            "grouping_files": {g: str(p) for g, p in grouping_files.items()},
            "feature_columns": list(dev1.FEATURE_COLUMNS),
            "feature_columns_sha256": _sha256_columns(dev1.FEATURE_COLUMNS),
            "compiler_version": compiler_version,
            "elapsed_seconds": round(finished - started, 3),
        }
    finally:
        for fh in list(writers.values()) + list(group_writers.values()):
            fh.close()


def _read_pilot_features(path: Path, expected_columns: list[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    if header != expected_columns + ["label"]:
        raise PilotStop("PILOT feature header drifted from DEV-1 schema")
    X = np.asarray([[float(c) for c in r[:-1]] for r in body], dtype=np.float64)
    y = np.asarray([int(r[-1]) for r in body], dtype=np.int64)
    if not np.all(np.isfinite(X)):
        raise PilotStop("PILOT feature contains NaN/Inf")
    return X, y, header


def _read_grouping(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pilot_admission(
    gen: dict[str, Any],
    dev1_root: Path,
    private_root: Path,
    expected_columns: list[str],
) -> dict[str, Any]:
    """Full data admission for 51 PILOT pairs; stop on any violation."""
    # DEV pair IDs must not overlap PILOT pair IDs.
    dev1_manifest = _read_json(Path(dev1_root) / "manifest.json")
    dev_pair_ids = {p["pair"]["pair_id"] for p in dev1_manifest.get("pairs", [])}
    pilot_pair_ids = {p["pair_id"] for p in gen["pairs"]}
    overlap = dev_pair_ids & pilot_pair_ids
    if overlap:
        raise PilotStop(f"PILOT/DEV pair overlap: {sorted(overlap)[:5]}")

    data: dict[str, Any] = {}
    grouping_maps: dict[str, dict[str, dict[str, int]]] = {}
    for group in ("C1", "C2"):
        X, y, header = _read_pilot_features(
            Path(gen["feature_files"][group]), expected_columns
        )
        grouping = _read_grouping(Path(gen["grouping_files"][group]))
        if X.shape[0] != 2 * PILOT_PAIRS or y.shape[0] != X.shape[0]:
            raise PilotStop(f"{group} rows != 2*51")
        if int((y == 0).sum()) != PILOT_PAIRS or int((y == 1).sum()) != PILOT_PAIRS:
            raise PilotStop(f"{group} label counts != 51/51")
        pmap: dict[str, dict[str, int]] = {}
        for g in grouping:
            state, pid, ridx = g["acl_state"], g["pair_id"], int(g["row_index"])
            if state not in ("A0", "A1"):
                raise PilotStop("invalid acl_state in grouping")
            expected_label = "0" if state == "A0" else "1"
            if g["label"] != expected_label or str(y[ridx]) != expected_label:
                raise PilotStop("grouping/feature label mismatch")
            pmap.setdefault(pid, {})[state] = ridx
        if set(pmap) != pilot_pair_ids or len(pmap) != PILOT_PAIRS:
            raise PilotStop(f"{group} pair map mismatch")
        for pid, states in pmap.items():
            if set(states) != {"A0", "A1"}:
                raise PilotStop(f"{group} pair {pid} missing A0/A1")
        grouping_maps[group] = pmap
        data[group] = {"X": X, "y": y, "header": header}

    if grouping_maps["C1"] != grouping_maps["C2"]:
        raise PilotStop("C1/C2 pair mapping inconsistent")

    # A0/A1 differ only in target authorization bit: verify from generation invariants.
    for p in gen["pairs"]:
        inv = p["invariant"]
        if not (inv["diff_exactly_target"] and inv["non_target_bits_equal"]
                and inv["a0_target_unauthorized"] and inv["a1_target_authorized"]):
            raise PilotStop(f"target-bit pairing invariant failed: {p['pair_id']}")

    return {
        "rows_per_group": 2 * PILOT_PAIRS,
        "label_counts": {"0": PILOT_PAIRS, "1": PILOT_PAIRS},
        "pilot_pairs": PILOT_PAIRS,
        "dev_pair_ids_count": len(dev_pair_ids),
        "pair_overlap_count": len(overlap),
        "pilot_pair_ids": sorted(pilot_pair_ids),
        "feature_columns_sha256": _sha256_columns(expected_columns),
        "invisible_pairs_kept": gen["invisible_pairs_kept"],
        "data": data,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run_pilot(
    dev1_root: Path,
    dev2_root: Path,
    private_root: Path,
) -> dict[str, Any]:
    dev1_root, dev2_root = Path(dev1_root), Path(dev2_root)
    private = _assert_private_root(private_root)
    logs: list[str] = []

    def log(msg: str) -> None:
        logs.append(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {msg}")

    started = time.time()
    try:
        dev1 = _import_dev1()
        dev2 = _load_module("dev2_pilot_reuse", DEV2_MODULE_PATH)
        log("imported DEV-1 atomic primitives and DEV-2 digest helpers")

        # 1) verify frozen artifacts BEFORE generation/prediction
        checks = verify_frozen_artifacts(dev1_root, dev2_root, dev2)
        _write_json(private / "frozen_model_load_check.json", checks)
        log("frozen artifact digests and config SHA verified")

        # 2) generate 51 independent PILOT pairs with PILOT- prefix
        gen = generate_pilot_pairs(private, dev1, PILOT_PAIRS)
        _write_json(private / "pilot_generation.json", gen)
        log(f"generated {gen['valid_pairs']} PILOT pairs in namespace={PILOT_NAMESPACE}")

        # 3) data admission (schema, labels, no overlap, target-bit pairing)
        expected_columns = list(dev1.FEATURE_COLUMNS)
        adm = pilot_admission(gen, dev1_root, private, expected_columns)
        admission_public = {k: v for k, v in adm.items() if k != "data"}
        _write_json(private / "pilot_admission.json", admission_public)
        log("PILOT admission PASS (51 pairs, no DEV overlap, schema identical)")

        # 4) load frozen models read-only and predict
        predictors, meta_check = load_frozen_predictors(dev2_root, dev2, expected_columns)
        load_check = dict(checks)
        load_check["models"] = meta_check
        load_check["no_refit"] = {
            "wrapper_has_fit": hasattr(predictors["C1"], "fit"),
            "wrapper_has_fit_transform": hasattr(predictors["C1"], "fit_transform"),
            "threshold": DECISION_THRESHOLD,
        }
        if load_check["no_refit"]["wrapper_has_fit"] or load_check["no_refit"]["wrapper_has_fit_transform"]:
            raise PilotStop("frozen predictor exposes a fit method")
        _write_json(private / "frozen_model_load_check.json", load_check)
        log("frozen models loaded read-only; no fit method exposed")

        # 5) pair scores -> d_i, write private per-pair differences
        # C1/C2 pair maps are byte-identical (verified in admission); use one map.
        grouping = _read_grouping(Path(gen["grouping_files"]["C1"]))
        pid_rows: dict[str, dict[str, int]] = {}
        for row in grouping:
            pid_rows.setdefault(row["pair_id"], {})[row["acl_state"]] = int(row["row_index"])

        diff_path = private / "pilot_pair_differences_private.csv"
        all_scores: dict[str, Any] = {"s_C1": [], "s_C2": [], "d_i": []}
        with diff_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["pair_id", "s_C1", "s_C2", "d_i"])
            for pid in admission_public["pilot_pair_ids"]:
                r0 = pid_rows[pid]["A0"]
                r1 = pid_rows[pid]["A1"]
                pair_result: dict[str, float] = {}
                for group in ("C1", "C2"):
                    # Same pair -> aligned A0/A1 rows in both feature sets.
                    X = adm["data"][group]["X"]
                    y = adm["data"][group]["y"]
                    pred = predictors[group].predict_labels(X[[r0, r1]])
                    c0 = int(pred[0] == int(y[r0]))
                    c1 = int(pred[1] == int(y[r1]))
                    pair_result[group] = pair_score(c0, c1)
                s1, s2 = pair_result["C1"], pair_result["C2"]
                di = pair_difference(s1, s2)
                all_scores["s_C1"].append(s1)
                all_scores["s_C2"].append(s2)
                all_scores["d_i"].append(di)
                w.writerow([pid, f"{s1:.6f}", f"{s2:.6f}", f"{di:.6f}"])
        log("pair scores and d_i computed from frozen predictions")

        # 6) single permitted statistical analysis
        n = len(all_scores["d_i"])
        if n != PILOT_PAIRS:
            raise PilotStop(f"difference count {n} != {PILOT_PAIRS}")
        var_sq = estimate_variance_sq(all_scores["d_i"])
        n_confirm = confirm_sample_size(var_sq)
        result = {
            "stage": STAGE,
            "n_pairs": n,
            "sigma_d_sq_ddof1": var_sq,
            "sigma_d": math.sqrt(var_sq),
            "variance_formula": "1/(n-1) * sum((d_i - mean(d))^2), ddof=1",
            "N_confirm": n_confirm,
            "confirm_formula": "ceil(max(618.26 * sigma_d_sq, 30))",
            "no_h1_test": True,
            "no_confirmatory_ci": True,
            "no_model_change": True,
        }
        _write_json(private / "pilot_variance_result.json", result)
        log(f"sigma_d^2={var_sq:.10f}; N_confirm={n_confirm}")

        # 7) manifest + environment
        env = {
            "stage": STAGE,
            "dev2_baseline_commit": "1850b28bfbc9a99814a58806ae603091702757a4",
            "dev1_manifest_sha256": admission_public_dev1_sha(dev1_root),
            "dev2_freeze_manifest_sha256": EXPECTED_DEV2_MANIFEST_SHA,
            "c1_model_artifact_sha256": EXPECTED_ARTIFACT_SHA["C1"],
            "c2_model_artifact_sha256": EXPECTED_ARTIFACT_SHA["C2"],
            "pilot_namespace": PILOT_NAMESPACE,
            "pair_count": PILOT_PAIRS,
            "feature_schema_sha256": DEV1_COLUMNS_SHA256,
            "generation_config": {
                "n_members": dev1.N_MEMBERS, "n_queries": dev1.N_QUERIES,
                "target": TARGET_INDEX, "target_label": TARGET_LABEL,
                "base_acl_rng": "secrets.randbelow (system CSPRNG, never seeded)",
                "namespace": PILOT_NAMESPACE,
            },
            "statistical_config": {
                "d_definition": "d_i = s_C2,i - s_C1,i; s_Cj=(I_A0+I_A1)/2",
                "variance_ddof": 1,
                "confirm_formula": "ceil(max(618.26*sigma_d_sq, 30))",
                "decision_threshold": DECISION_THRESHOLD,
            },
            "software": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
            "timestamps": {
                "started_epoch": started,
                "finished_epoch": time.time(),
                "started_local": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
            },
        }
        _write_json(private / "environment.json", env)
        manifest = {
            "stage": STAGE,
            "status": "PILOT_READY",
            "dev2_baseline_commit": env["dev2_baseline_commit"],
            "dev1_manifest_digest": env["dev1_manifest_sha256"],
            "dev2_freeze_manifest_digest": EXPECTED_DEV2_MANIFEST_SHA,
            "model_artifact_digests": dict(EXPECTED_ARTIFACT_SHA),
            "pilot_namespace": PILOT_NAMESPACE,
            "pair_count": PILOT_PAIRS,
            "feature_schema_digest": DEV1_COLUMNS_SHA256,
            "frozen_load_check": load_check,
            "data_admission": admission_public,
            "variance_result": result,
            "private_files": {
                "pilot_C1_features": gen["feature_files"]["C1"],
                "pilot_C2_features": gen["feature_files"]["C2"],
                "pilot_C1_grouping": gen["grouping_files"]["C1"],
                "pilot_C2_grouping": gen["grouping_files"]["C2"],
                "pair_differences": str(diff_path),
            },
            "stage_boundary": {
                "h1_tested": False, "confirmatory_ci": False, "model_changed": False,
                "new_model_trained": False, "pilot_pairs_appended": False,
                "confirm_run": False, "stability_seeds": False,
            },
        }
        _write_json(private / "pilot_manifest.json", manifest)
        log("pilot_manifest written; status PILOT_READY")

        return {
            "status": "PILOT_READY",
            "n_pairs": n,
            "sigma_d_sq_ddof1": var_sq,
            "N_confirm": n_confirm,
            "pair_overlap": admission_public["pair_overlap_count"],
            "invisible_pairs_kept": len(gen["invisible_pairs_kept"]),
            "manifest_sha256": _sha256_file(private / "pilot_manifest.json"),
        }
    except PilotStop as exc:
        log(f"STOP: {exc}")
        _write_json(private / "pilot_failure.json", {"error": str(exc), "logs": logs})
        raise
    finally:
        (private / "execution.log").write_text("\n".join(logs) + "\n", encoding="utf-8")


def admission_public_dev1_sha(dev1_root: Path) -> str:
    return _sha256_file(Path(dev1_root) / "manifest.json")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev1-root", type=Path, default=DEV1_PRIVATE_DEFAULT)
    parser.add_argument("--dev2-root", type=Path, default=DEV2_PRIVATE_DEFAULT)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_pilot(args.dev1_root, args.dev2_root, args.private_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
