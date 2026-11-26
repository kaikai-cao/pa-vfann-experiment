"""H1-RM.3A.13 - CONFIRM: one-shot confirmatory evaluation of frozen C1/C2.

Scope (strict, frozen by H1-RM.3A.13 task package and PROTOCOL.md erratum R1):
  * Generate exactly 30 NEW independent ACL pairs in a distinct CONFIRM namespace.
  * Reuse DEV-1 frozen atomic primitives BY IMPORT (never copy/modify their logic).
  * Verify DEV-2 frozen artifacts/config/schema and that they match PILOT's record.
  * Verify CONFIRM pair IDs and base-ACL digests are disjoint from BOTH DEV and PILOT.
  * Load DEV-2 frozen C1/C2 read-only; ONLY scaler.transform + predict_proba at
    threshold 0.5.  No fit / fit_transform / partial_fit / model selection.
  * Run C0/C1/C2 harness per pair; C0 is search/trace control ONLY (no BA_C0).
  * One pair-level d_i = s_C2,i - s_C1,i; BA_C1/BA_C2/Delta_BA.
  * B=10000 paired bootstrap (pair = resampling unit, A0/A1 kept together, C1/C2
    share the same resampled pairs).  Percentile intervals primary, BCa auxiliary,
    report proportion Delta_BA<=0.  Bootstrap seed frozen BEFORE any CONFIRM result
    is read; no seed search, no reruns.
  * Report TPR/FPR, natural-prior (p=0.1) accuracy/precision, target visibility
    (auxiliary stratification only), C0/C1 trace contrast, C2 stop-observer
    differences, and internal K-hit -> observer-trace separation.
  * No H1 verdict produced here beyond the pre-registered statistical/practical
    decision flags; no physical page-level claim.

All private artifacts are written to a caller-supplied directory OUTSIDE the repo.
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
from typing import Any, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Frozen constants - mirror DEV-1/DEV-2/PILOT and PROTOCOL.md; never new design.
# --------------------------------------------------------------------------- #

STAGE = "H1-RM.3A.13"
CONFIRM_NAMESPACE = "CONFIRM"
CONFIRM_PAIRS = 30
TARGET_INDEX = 103
TARGET_LABEL = 101751
DECISION_THRESHOLD = 0.5

BOOTSTRAP_B = 10000
# Frozen before any CONFIRM result is read; no CLI override, no seed search.
BOOTSTRAP_SEED = 20261126
SESOI_DELTA = 0.10
NATURAL_PRIOR_P = 0.1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV1_MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a10_dev1_data_pipeline" / "dev1_pipeline.py"
PILOT_MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a12_pilot_variance" / "pilot_variance.py"
DEV2_MODULE_PATH = REPO_ROOT / "experiments" / "h1_rm_3a11_dev2_model_freeze" / "dev2_model_freeze.py"

DEV1_PRIVATE_DEFAULT = Path(r"D:/Research/pa-vfann-h1-rm3a10-dev1-private-v2")
DEV2_PRIVATE_DEFAULT = Path(r"D:/Research/pa-vfann-h1-rm3a11-dev2-private-v1")
PILOT_PRIVATE_DEFAULT = Path(r"D:/Research/pa-vfann-h1-rm3a12-pilot-private-v1")


class ConfirmStop(RuntimeError):
    """Raised on any frozen-boundary or data-admission violation."""


# --------------------------------------------------------------------------- #
# Generic helpers (independent of experiment state)
# --------------------------------------------------------------------------- #

def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(path))
    if spec is None or spec.loader is None:
        raise ConfirmStop(f"cannot load module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _import_dev1() -> Any:
    return _load_module("dev1_confirm_reuse", DEV1_MODULE_PATH)


def _import_pilot() -> Any:
    return _load_module("pilot_confirm_reuse", PILOT_MODULE_PATH)


def _import_dev2() -> Any:
    return _load_module("dev2_confirm_reuse", DEV2_MODULE_PATH)


def _sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_columns(columns: Sequence[str]) -> str:
    import hashlib
    return hashlib.sha256(("\n".join(list(columns)) + "\n").encode("utf-8")).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_private_root(private_root: Path) -> Path:
    root = Path(private_root).resolve()
    repo = REPO_ROOT.resolve()
    if root == repo or repo in root.parents:
        raise ConfirmStop("private_root must be OUTSIDE the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------- #
# Frozen-input verification (reuse PILOT verifier; add PILOT-consistency check)
# --------------------------------------------------------------------------- #

def verify_frozen_inputs(
    dev1_root: Path,
    dev2_root: Path,
    pilot_root: Path,
    pilot: Any,
    dev2: Any,
) -> dict[str, Any]:
    """Verify DEV-2 artifacts/config/schema AND that they match PILOT's record."""
    dev1_root, dev2_root, pilot_root = Path(dev1_root), Path(dev2_root), Path(pilot_root)
    checks = dict(pilot.verify_frozen_artifacts(dev1_root, dev2_root, dev2))

    pilot_manifest_path = pilot_root / "pilot_manifest.json"
    if not pilot_manifest_path.is_file():
        raise ConfirmStop("PILOT pilot_manifest.json missing")
    pilot_manifest = _read_json(pilot_manifest_path)
    checks["pilot_manifest_sha256"] = _sha256_file(pilot_manifest_path)

    if pilot_manifest.get("dev2_freeze_manifest_digest") != checks["dev2_manifest_sha256"]:
        raise ConfirmStop("PILOT-recorded DEV-2 manifest digest differs from current")
    if pilot_manifest.get("model_artifact_digests") != {
        s: checks[f"{s}_artifact_sha256"] for s in ("C1", "C2")
    }:
        raise ConfirmStop("PILOT-recorded model artifact digests differ from current")
    if pilot_manifest.get("feature_schema_digest") != pilot.DEV1_COLUMNS_SHA256:
        raise ConfirmStop("PILOT-recorded feature schema digest drifted")
    checks["pilot_consistent_with_dev2"] = True
    checks["status"] = "PASS"
    return checks


def collect_prior_digests(
    dev1_root: Path,
    pilot_root: Path,
) -> dict[str, Any]:
    """Collect DEV/PILOT pair IDs and base-ACL digests for disjointness checks."""
    dev1_manifest = _read_json(Path(dev1_root) / "manifest.json")
    pilot_generation = _read_json(Path(pilot_root) / "pilot_generation.json")

    dev_pairs = dev1_manifest.get("pairs", [])
    dev_ids = {p["pair"]["pair_id"] for p in dev_pairs}
    dev_digests = {p["pair"].get("base_acl_sha256") for p in dev_pairs}

    pilot_pairs = pilot_generation.get("pairs", [])
    pilot_ids = {p.get("pair_id") for p in pilot_pairs}
    pilot_digests = {p.get("base_acl_sha256") for p in pilot_pairs}

    if None in dev_digests or None in pilot_digests:
        raise ConfirmStop("prior base_acl_sha256 contains a missing value")
    if len(dev_ids) != len(dev_pairs) or len(pilot_ids) != len(pilot_pairs):
        raise ConfirmStop("prior pair IDs are not unique")

    return {
        "dev_pair_ids": dev_ids,
        "dev_base_acl_digests": dev_digests,
        "pilot_pair_ids": pilot_ids,
        "pilot_base_acl_digests": pilot_digests,
    }


# --------------------------------------------------------------------------- #
# CONFIRM data generation - reuse DEV-1 atomic functions by import
# --------------------------------------------------------------------------- #

def _count_stop_events(events: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {"stop_check": 0, "search_stop": 0}
    for e in events:
        t = e.get("event_type")
        if t in counts:
            counts[t] += 1
    return counts


def confirm_generate_pairs(
    private_root: Path,
    dev1: Any,
    prior: dict[str, Any],
    target_pairs: int = CONFIRM_PAIRS,
) -> dict[str, Any]:
    """Generate 30 CONFIRM pairs (CONFIRM- prefix, CSPRNG), disjoint from DEV/PILOT."""
    private = _assert_private_root(private_root)
    constants = dev1.validate_frozen_constants()
    if constants["target"] != TARGET_INDEX or constants["target_label"] != TARGET_LABEL:
        raise ConfirmStop("frozen target drifted from u=103/label=101751")
    if target_pairs != CONFIRM_PAIRS:
        raise ConfirmStop("CONFIRM pair count is frozen at 30; no append/skip")

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
    for group in ("C1", "C2"):  # C0 kept as trace control only; never a model input
        feature_files[group] = features_dir / f"confirm_{group}_features.csv"
        grouping_files[group] = features_dir / f"confirm_{group}_grouping_private.csv"
        writers[group] = feature_files[group].open("w", newline="", encoding="utf-8")
        group_writers[group] = grouping_files[group].open("w", newline="", encoding="utf-8")
        csv.writer(writers[group]).writerow(feature_headers)
        csv.writer(group_writers[group]).writerow(["row_index", "pair_id", "acl_state", "label"])

    used_ids: set[str] = set()
    used_digests: set[str] = set()
    pairs_summary: list[dict[str, Any]] = []
    invisible_pairs: list[str] = []
    descriptive: list[dict[str, Any]] = []
    valid = 0
    attempt = 0
    started = time.time()
    try:
        while valid < target_pairs:
            attempt += 1
            pair_id = f"{CONFIRM_NAMESPACE}-{attempt:06d}"
            pair_dir = runs_root / pair_id
            try:
                pair = dev1.build_dev_pair(pair_dir, pair_id)
                structure, observer_events = dev1.run_one_pair(pair, harness, loader, runs_root)

                summary = pair.safe_summary()
                base_digest = summary["base_acl_sha256"]
                # Three-way disjointness, enforced at generation time.
                if pair_id in prior["dev_pair_ids"] or pair_id in prior["pilot_pair_ids"]:
                    raise ConfirmStop(f"CONFIRM pair ID collides with DEV/PILOT: {pair_id}")
                if (base_digest in prior["dev_base_acl_digests"]
                        or base_digest in prior["pilot_base_acl_digests"]):
                    raise ConfirmStop(f"CONFIRM base ACL digest collides with DEV/PILOT: {pair_id}")
                if pair_id in used_ids or base_digest in used_digests:
                    raise ConfirmStop(f"CONFIRM internal duplicate: {pair_id}")
                used_ids.add(pair_id)
                used_digests.add(base_digest)

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

                inv = structure["invariant"]
                if not (inv["diff_exactly_target"] and inv["non_target_bits_equal"]
                        and inv["a0_target_unauthorized"] and inv["a1_target_authorized"]):
                    raise ConfirmStop(f"target-bit pairing invariant failed: {pair_id}")

                vis = structure["target_visibility"]
                any_visible = any(
                    vis[g][s]["observer_visible"] for g in ("C0", "C1", "C2") for s in ("A0", "A1")
                )
                pairs_summary.append({
                    "pair_id": pair_id,
                    "base_acl_sha256": base_digest,
                    "a0_blob_sha256": summary["a0_blob_sha256"],
                    "a1_blob_sha256": summary["a1_blob_sha256"],
                    "invariant": inv,
                    "target_observer_visible": any_visible,
                    "harness_c2_khit_seen": {
                        s: bool(structure["harness"][s]["c2_khit_seen"]) for s in ("A0", "A1")
                    },
                })
                if not any_visible:
                    invisible_pairs.append(pair_id)

                # Descriptive observer evidence, kept strictly separate from model input.
                c0_events = {s: observer_events["C0"][s] for s in ("A0", "A1")}
                c1_events = {s: observer_events["C1"][s] for s in ("A0", "A1")}
                c2_stop = {
                    s: _count_stop_events(observer_events["C2"][s]) for s in ("A0", "A1")
                }
                descriptive.append({
                    "pair_id": pair_id,
                    "c0_c1_observer_event_count": {
                        s: [len(c0_events[s]), len(c1_events[s])] for s in ("A0", "A1")
                    },
                    "c0_c1_observer_identical": {
                        s: (json.dumps(c0_events[s], sort_keys=True)
                            == json.dumps(c1_events[s], sort_keys=True))
                        for s in ("A0", "A1")
                    },
                    "c2_stop_event_counts": c2_stop,
                    "c2_stop_observer_diff": any(
                        c2_stop["A0"][k] != c2_stop["A1"][k]
                        for k in ("stop_check", "search_stop")
                    ),
                })
                valid += 1
            except ConfirmStop:
                raise
            except (dev1.StructuralPairFailure, dev1.TechnicalPairFailure) as exc:
                fail = runs_root / pair_id / "failure.json"
                fail.parent.mkdir(parents=True, exist_ok=True)
                _write_json(fail, {"pair_id": pair_id, "stage": type(exc).__name__,
                                   "reason": str(exc), "timestamp": time.time()})
                raise ConfirmStop(f"CONFIRM pair {pair_id} structural/technical failure: {exc}")

        return {
            "namespace": CONFIRM_NAMESPACE,
            "target_pairs": target_pairs,
            "valid_pairs": valid,
            "attempts": attempt,
            "invisible_pairs_kept": invisible_pairs,
            "pairs": pairs_summary,
            "descriptive": descriptive,
            "feature_files": {g: str(p) for g, p in feature_files.items()},
            "grouping_files": {g: str(p) for g, p in grouping_files.items()},
            "feature_columns": list(dev1.FEATURE_COLUMNS),
            "feature_columns_sha256": _sha256_columns(dev1.FEATURE_COLUMNS),
            "compiler_version": compiler_version,
            "elapsed_seconds": round(time.time() - started, 3),
        }
    finally:
        for fh in list(writers.values()) + list(group_writers.values()):
            fh.close()


# --------------------------------------------------------------------------- #
# Data admission
# --------------------------------------------------------------------------- #

def confirm_admission(
    gen: dict[str, Any],
    prior: dict[str, Any],
    expected_columns: Sequence[str],
    pilot: Any,
) -> dict[str, Any]:
    """Full data admission for 30 CONFIRM pairs; stop on any violation; no filtering."""
    confirm_ids = {p["pair_id"] for p in gen["pairs"]}
    confirm_digests = {p["base_acl_sha256"] for p in gen["pairs"]}
    if gen["valid_pairs"] != CONFIRM_PAIRS or len(confirm_ids) != CONFIRM_PAIRS:
        raise ConfirmStop("CONFIRM pair count/IDs not exactly 30 unique")
    if len(confirm_digests) != CONFIRM_PAIRS:
        raise ConfirmStop("CONFIRM base ACL digests not unique")
    id_overlap = confirm_ids & (prior["dev_pair_ids"] | prior["pilot_pair_ids"])
    digest_overlap = confirm_digests & (prior["dev_base_acl_digests"]
                                        | prior["pilot_base_acl_digests"])
    if id_overlap or digest_overlap:
        raise ConfirmStop("CONFIRM overlaps DEV/PILOT (pair ID or base ACL digest)")

    data: dict[str, Any] = {}
    grouping_maps: dict[str, dict[str, dict[str, int]]] = {}
    for group in ("C1", "C2"):
        X, y, header = pilot._read_pilot_features(
            Path(gen["feature_files"][group]), list(expected_columns)
        )
        grouping = pilot._read_grouping(Path(gen["grouping_files"][group]))
        if X.shape[0] != 2 * CONFIRM_PAIRS:
            raise ConfirmStop(f"{group} rows != 60")
        if int((y == 0).sum()) != CONFIRM_PAIRS or int((y == 1).sum()) != CONFIRM_PAIRS:
            raise ConfirmStop(f"{group} label counts != 30/30")
        pmap: dict[str, dict[str, int]] = {}
        for g in grouping:
            state, pid, ridx = g["acl_state"], g["pair_id"], int(g["row_index"])
            if state not in ("A0", "A1"):
                raise ConfirmStop("invalid acl_state in grouping")
            expected_label = "0" if state == "A0" else "1"
            if g["label"] != expected_label or str(y[ridx]) != expected_label:
                raise ConfirmStop("grouping/feature label mismatch")
            pmap.setdefault(pid, {})[state] = ridx
        if set(pmap) != confirm_ids or len(pmap) != CONFIRM_PAIRS:
            raise ConfirmStop(f"{group} pair map mismatch")
        for pid, states in pmap.items():
            if set(states) != {"A0", "A1"}:
                raise ConfirmStop(f"{group} pair {pid} missing A0/A1")
        grouping_maps[group] = pmap
        data[group] = {"X": X, "y": y, "header": header}
    if grouping_maps["C1"] != grouping_maps["C2"]:
        raise ConfirmStop("C1/C2 pair mapping inconsistent")

    for p in gen["pairs"]:
        inv = p["invariant"]
        if not (inv["diff_exactly_target"] and inv["non_target_bits_equal"]
                and inv["a0_target_unauthorized"] and inv["a1_target_authorized"]):
            raise ConfirmStop(f"target-bit pairing invariant failed: {p['pair_id']}")

    return {
        "confirm_pairs": CONFIRM_PAIRS,
        "rows_per_group": 2 * CONFIRM_PAIRS,
        "label_counts": {"0": CONFIRM_PAIRS, "1": CONFIRM_PAIRS},
        "pair_id_overlap_count": len(id_overlap),
        "base_acl_digest_overlap_count": len(digest_overlap),
        "dev_pair_ids_count": len(prior["dev_pair_ids"]),
        "pilot_pair_ids_count": len(prior["pilot_pair_ids"]),
        "confirm_pair_ids": sorted(confirm_ids),
        "feature_columns_sha256": _sha256_columns(expected_columns),
        "invisible_pairs_kept": gen["invisible_pairs_kept"],
        "data": data,
        "grouping_maps": grouping_maps,
    }


# --------------------------------------------------------------------------- #
# Frozen-model inference -> per-pair indicators (no fit anywhere)
# --------------------------------------------------------------------------- #

def compute_pair_indicators(
    adm: dict[str, Any],
    predictors: dict[str, Any],
    pilot: Any,
) -> list[dict[str, Any]]:
    """For each pair record I_{C,s} and s/d using frozen predictors only."""
    grouping = adm["grouping_maps"]["C1"]
    rows: list[dict[str, Any]] = []
    for pid in adm["confirm_pair_ids"]:
        r0, r1 = grouping[pid]["A0"], grouping[pid]["A1"]
        indicators: dict[str, int] = {}
        for group in ("C1", "C2"):
            X, y = adm["data"][group]["X"], adm["data"][group]["y"]
            pred = predictors[group].predict_labels(X[[r0, r1]])
            indicators[f"I_{group}_A0"] = int(pred[0] == int(y[r0]))
            indicators[f"I_{group}_A1"] = int(pred[1] == int(y[r1]))
        s1 = pilot.pair_score(indicators["I_C1_A0"], indicators["I_C1_A1"])
        s2 = pilot.pair_score(indicators["I_C2_A0"], indicators["I_C2_A1"])
        rows.append({
            "pair_id": pid,
            **indicators,
            "s_C1": float(s1),
            "s_C2": float(s2),
            "d_i": float(pilot.pair_difference(s1, s2)),
        })
    return rows


# --------------------------------------------------------------------------- #
# Paired bootstrap (pure; scipy used only for normal quantiles)
# --------------------------------------------------------------------------- #

def _norm_ppf(q: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(q))


def _norm_cdf(z: float) -> float:
    from scipy.stats import norm
    return float(norm.cdf(z))


def paired_bootstrap(
    indicators: Sequence[dict[str, Any]],
    seed: int = BOOTSTRAP_SEED,
    B: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Pair-level paired bootstrap; C1/C2 share the same resampled pairs."""
    n = len(indicators)
    if n != CONFIRM_PAIRS or B < 1:
        raise ConfirmStop("bootstrap requires 30 pairs and B>=1")
    d = np.asarray([float(r["d_i"]) for r in indicators], dtype=np.float64)
    s1 = np.asarray([float(r["s_C1"]) for r in indicators], dtype=np.float64)
    s2 = np.asarray([float(r["s_C2"]) for r in indicators], dtype=np.float64)
    if not (np.all(np.isfinite(d)) and np.all(np.isfinite(s1)) and np.all(np.isfinite(s2))):
        raise ConfirmStop("non-finite pair indicator in bootstrap")

    point_delta = float(np.mean(d))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(B, n))  # with replacement; pairs kept whole
    boot_delta = d[idx].mean(axis=1)
    boot_ba1 = s1[idx].mean(axis=1)
    boot_ba2 = s2[idx].mean(axis=1)

    def pct(arr: np.ndarray, q: float) -> float:
        return float(np.percentile(arr, q))

    result: dict[str, Any] = {
        "B": B,
        "seed": seed,
        "resampling_unit": "ACL pair (A0/A1 kept together; C1/C2 same resampled pairs)",
        "point_delta_ba": point_delta,
        "percentile_90": [pct(boot_delta, 5.0), pct(boot_delta, 95.0)],
        "percentile_95": [pct(boot_delta, 2.5), pct(boot_delta, 97.5)],
        "q_0_05": pct(boot_delta, 5.0),
        "proportion_delta_le_0": float(np.mean(boot_delta <= 0)),
        "boot_ba_c1_mean": float(np.mean(boot_ba1)),
        "boot_ba_c2_mean": float(np.mean(boot_ba2)),
    }

    # BCa as auxiliary robustness check (never used as the primary decision).
    try:
        eps = 1.0 / (2.0 * B)
        prop = float(np.mean(boot_delta < point_delta))
        prop = min(max(prop, eps), 1.0 - eps)
        z0 = _norm_ppf(prop)
        jack = np.array([np.mean(np.delete(d, i)) for i in range(n)], dtype=np.float64)
        jd = jack.mean() - jack
        denom = 6.0 * (float(np.sum(jd ** 2)) ** 1.5)
        accel = float(np.sum(jd ** 3)) / denom if denom > 0 else 0.0

        def bca_q(alpha: float) -> float:
            z = _norm_ppf(alpha)
            adj = _norm_cdf(z0 + (z0 + z) / (1.0 - accel * (z0 + z)))
            adj = min(max(adj, 0.0), 1.0)
            return pct(boot_delta, adj * 100.0)

        result["bca_90"] = [bca_q(0.05), bca_q(0.95)]
        result["bca_95"] = [bca_q(0.025), bca_q(0.975)]
        result["bca_z0"] = z0
        result["bca_acceleration"] = accel
        result["bca_status"] = "OK"
    except Exception as exc:  # BCa is auxiliary; never block the primary result.
        result["bca_status"] = f"UNAVAILABLE: {exc}"
    return result


def compute_metrics(rows: Sequence[dict[str, Any]], boot: dict[str, Any]) -> dict[str, Any]:
    """BA/TPR/FPR/natural-prior/visibility/statistical decisions."""
    n = len(rows)
    if n != CONFIRM_PAIRS:
        raise ConfirmStop("metric computation requires 30 pairs")
    per_pair = {s: {"A0": 0, "A1": 0} for s in ("C1", "C2")}
    for r in rows:
        for s in ("C1", "C2"):
            per_pair[s]["A0"] += int(r[f"I_{s}_A0"])
            per_pair[s]["A1"] += int(r[f"I_{s}_A1"])
    out: dict[str, Any] = {"n_pairs": n, "per_strategy": {}}
    for s in ("C1", "C2"):
        tp, tn = per_pair[s]["A1"], per_pair[s]["A0"]
        tpr, tnr = tp / n, tn / n
        fpr = 1.0 - tnr
        ba = (tpr + tnr) / 2.0
        p = NATURAL_PRIOR_P
        denom = p * tpr + (1 - p) * fpr
        precision = (p * tpr / denom) if denom > 0 else None
        out["per_strategy"][s] = {
            "TP": tp, "TN": tn, "FN": n - tp, "FP": n - tn,
            "TPR": tpr, "TNR": tnr, "FPR": fpr, "BA": ba,
            "natural_prior_p": p,
            "natural_accuracy": p * tpr + (1 - p) * (1 - fpr),
            "natural_precision": precision,
        }
    ba1 = out["per_strategy"]["C1"]["BA"]
    ba2 = out["per_strategy"]["C2"]["BA"]
    delta = ba2 - ba1
    if not math.isclose(delta, boot["point_delta_ba"], abs_tol=1e-9):
        raise ConfirmStop("Delta_BA from indicators disagrees with bootstrap point")
    out["BA_C1"] = ba1
    out["BA_C2"] = ba2
    out["delta_ba"] = delta
    out["statistically_significant"] = bool(boot["q_0_05"] > 0)
    out["practically_significant"] = bool(delta >= SESOI_DELTA)
    out["primary_decision_rule"] = "q_0_05 > 0 (90% percentile lower bound, one-sided 0.05)"
    out["practical_rule"] = "Delta_BA >= 0.10"
    return out


# --------------------------------------------------------------------------- #
# Descriptive evidence (visibility / C0 trace / C2 stop / K-hit separation)
# --------------------------------------------------------------------------- #

def descriptive_summary(gen: dict[str, Any]) -> dict[str, Any]:
    desc = gen["descriptive"]
    n = len(desc)
    visible_ids = set(gen["invisible_pairs_kept"])
    invisible = len(visible_ids)
    c0c1_identical = sum(
        int(d["c0_c1_observer_identical"]["A0"]) + int(d["c0_c1_observer_identical"]["A1"])
        for d in desc
    ) / (2 * n)
    khit_any = sum(
        int(any(p["harness_c2_khit_seen"].values())) for p in gen["pairs"]
    )
    khit_both = sum(
        int(all(p["harness_c2_khit_seen"].values())) for p in gen["pairs"]
    )
    c2_stop_diff = sum(int(d["c2_stop_observer_diff"]) for d in desc)
    return {
        "n_pairs": n,
        "target_observer_visible_pairs": n - invisible,
        "target_observer_invisible_pairs": invisible,
        "target_observer_visible_ratio": (n - invisible) / n,
        "visibility_is_auxiliary_stratification_only": True,
        "c0_c1_observer_identical_fraction_states": c0c1_identical,
        "internal_c2_khit_triggered_any_state_pairs": khit_any,
        "internal_c2_khit_triggered_both_states_pairs": khit_both,
        "c2_stop_observer_diff_pairs": c2_stop_diff,
        "note": (
            "Internal K-hit trigger (harness stdout) and observer-trace difference "
            "(observer whitelist) are distinct layers; neither is an attack success."
        ),
    }


# --------------------------------------------------------------------------- #
# Main orchestration
# --------------------------------------------------------------------------- #

def run_confirm(
    dev1_root: Path,
    dev2_root: Path,
    pilot_root: Path,
    private_root: Path,
) -> dict[str, Any]:
    dev1_root, dev2_root, pilot_root = Path(dev1_root), Path(dev2_root), Path(pilot_root)
    private = _assert_private_root(private_root)
    logs: list[str] = []

    def log(msg: str) -> None:
        logs.append(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {msg}")

    started = time.time()
    try:
        dev1 = _import_dev1()
        pilot = _import_pilot()
        dev2 = _import_dev2()
        log("imported DEV-1/PILOT/DEV-2 helpers BY IMPORT (no logic copied)")

        # Freeze the bootstrap execution config BEFORE any CONFIRM result exists.
        frozen_exec = {
            "stage": STAGE,
            "bootstrap_B": BOOTSTRAP_B,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "resampling_unit": "pair",
            "interval_primary": "percentile",
            "interval_auxiliary": "BCa",
            "primary_rule": "q_0_05 > 0",
            "sesoi_delta": SESOI_DELTA,
            "decision_threshold": DECISION_THRESHOLD,
            "natural_prior_p": NATURAL_PRIOR_P,
            "confirm_pairs": CONFIRM_PAIRS,
            "no_seed_search": True,
            "no_rerun": True,
        }
        _write_json(private / "frozen_execution_config.json", frozen_exec)
        log("frozen execution config written before reading any CONFIRM result")

        checks = verify_frozen_inputs(dev1_root, dev2_root, pilot_root, pilot, dev2)
        _write_json(private / "frozen_model_load_check.json", checks)
        log("DEV-2 artifacts/config/schema verified AND consistent with PILOT record")

        prior = collect_prior_digests(dev1_root, pilot_root)
        log("collected DEV/PILOT pair IDs and base-ACL digests for disjointness")

        expected_columns = list(dev1.FEATURE_COLUMNS)
        gen = confirm_generate_pairs(private, dev1, prior, CONFIRM_PAIRS)
        _write_json(private / "confirm_generation.json", gen)
        log(f"generated {gen['valid_pairs']} CONFIRM pairs, namespace={CONFIRM_NAMESPACE}, disjoint from DEV/PILOT")

        adm = confirm_admission(gen, prior, expected_columns, pilot)
        admission_public = {k: v for k, v in adm.items() if k not in ("data", "grouping_maps")}
        _write_json(private / "confirm_admission.json", admission_public)
        log("CONFIRM admission PASS (30 pairs, 3-way disjoint, schema identical, no filtering)")

        predictors, meta_check = pilot.load_frozen_predictors(dev2_root, dev2, expected_columns)
        load_check = dict(checks)
        load_check["models"] = meta_check
        load_check["no_refit"] = {
            "wrapper_has_fit": any(hasattr(predictors[s], "fit") for s in ("C1", "C2")),
            "wrapper_has_fit_transform": any(
                hasattr(predictors[s], "fit_transform") for s in ("C1", "C2")
            ),
            "wrapper_has_partial_fit": any(
                hasattr(predictors[s], "partial_fit") for s in ("C1", "C2")
            ),
            "threshold": DECISION_THRESHOLD,
        }
        if any(load_check["no_refit"][k] for k in ("wrapper_has_fit",
                                                   "wrapper_has_fit_transform",
                                                   "wrapper_has_partial_fit")):
            raise ConfirmStop("frozen predictor exposes a fit method")
        _write_json(private / "frozen_model_load_check.json", load_check)
        log("frozen C1/C2 loaded read-only; inference path has no fit")

        rows = compute_pair_indicators(adm, predictors, pilot)
        diff_path = private / "confirm_pair_results_private.csv"
        with diff_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["pair_id", "I_C1_A0", "I_C1_A1", "I_C2_A0", "I_C2_A1",
                        "s_C1", "s_C2", "d_i"])
            for r in rows:
                w.writerow([r["pair_id"], r["I_C1_A0"], r["I_C1_A1"],
                            r["I_C2_A0"], r["I_C2_A1"],
                            f"{r['s_C1']:.6f}", f"{r['s_C2']:.6f}", f"{r['d_i']:.6f}"])
        log("per-pair indicators computed from frozen predictions")

        boot = paired_bootstrap(rows, BOOTSTRAP_SEED, BOOTSTRAP_B)
        _write_json(private / "confirm_bootstrap_private.json", boot)
        log(f"paired bootstrap done: B={boot['B']}, q_0_05={boot['q_0_05']:.6f}")

        metrics = compute_metrics(rows, boot)
        metrics["descriptive_evidence"] = descriptive_summary(gen)
        _write_json(private / "confirm_statistics.json", metrics)
        log(f"BA_C1={metrics['BA_C1']:.6f} BA_C2={metrics['BA_C2']:.6f} Delta={metrics['delta_ba']:.6f}")

        env = {
            "stage": STAGE,
            "dev1_manifest_sha256": pilot.admission_public_dev1_sha(dev1_root),
            "dev2_freeze_manifest_sha256": checks["dev2_manifest_sha256"],
            "pilot_manifest_sha256": checks["pilot_manifest_sha256"],
            "model_artifact_digests": {
                s: checks[f"{s}_artifact_sha256"] for s in ("C1", "C2")
            },
            "config_sha256": checks["config_sha256_recomputed"],
            "feature_schema_sha256": checks["feature_schema_columns_sha256"],
            "confirm_namespace": CONFIRM_NAMESPACE,
            "pair_count": CONFIRM_PAIRS,
            "generation_config": {
                "n_members": dev1.N_MEMBERS, "n_queries": dev1.N_QUERIES,
                "target": TARGET_INDEX, "target_label": TARGET_LABEL,
                "base_acl_rng": "secrets.randbelow (system CSPRNG, never seeded)",
                "namespace": CONFIRM_NAMESPACE,
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
            "status": "CONFIRM_COMPLETE",
            "baseline_protocol_commit": "16d103a6f08d110afa8533372746708a3e92e0cd",
            "dev1_manifest_digest": env["dev1_manifest_sha256"],
            "dev2_freeze_manifest_digest": env["dev2_freeze_manifest_sha256"],
            "pilot_manifest_digest": env["pilot_manifest_sha256"],
            "model_artifact_digests": env["model_artifact_digests"],
            "config_sha256": env["config_sha256"],
            "feature_schema_digest": env["feature_schema_sha256"],
            "confirm_namespace": CONFIRM_NAMESPACE,
            "pair_count": CONFIRM_PAIRS,
            "frozen_execution_config_sha256": _sha256_file(private / "frozen_execution_config.json"),
            "frozen_load_check": load_check,
            "data_admission": admission_public,
            "pair_indicators_file": str(diff_path),
            "bootstrap": boot,
            "statistics": metrics,
            "environment": env,
            "private_files": {
                "confirm_C1_features": gen["feature_files"]["C1"],
                "confirm_C2_features": gen["feature_files"]["C2"],
                "confirm_C1_grouping": gen["grouping_files"]["C1"],
                "confirm_C2_grouping": gen["grouping_files"]["C2"],
                "generation": str(private / "confirm_generation.json"),
            },
            "stage_boundary": {
                "protocol_changed": False,
                "model_retrained": False,
                "model_selected_or_tuned": False,
                "c0_classifier_trained": False,
                "ba_c0_reported": False,
                "pilot_pairs_reused": False,
                "dev_pairs_reused": False,
                "pairs_appended_or_filtered": False,
                "query_level_unit": False,
                "physical_page_trace_claim": False,
                "h1_global_verdict": "CONDITIONAL",
            },
        }
        _write_json(private / "confirm_manifest.json", manifest)
        log("confirm_manifest written; status CONFIRM_COMPLETE")

        return {
            "status": "CONFIRM_COMPLETE",
            "n_pairs": CONFIRM_PAIRS,
            "BA_C1": metrics["BA_C1"],
            "BA_C2": metrics["BA_C2"],
            "delta_ba": metrics["delta_ba"],
            "q_0_05": boot["q_0_05"],
            "percentile_90": boot["percentile_90"],
            "statistically_significant": metrics["statistically_significant"],
            "practically_significant": metrics["practically_significant"],
            "pair_overlap": admission_public["pair_id_overlap_count"],
            "digest_overlap": admission_public["base_acl_digest_overlap_count"],
            "B": boot["B"],
            "manifest_sha256": _sha256_file(private / "confirm_manifest.json"),
        }
    except ConfirmStop as exc:
        log(f"STOP: {exc}")
        _write_json(private / "confirm_failure.json", {"error": str(exc), "logs": logs})
        raise
    finally:
        (private / "execution.log").write_text("\n".join(logs) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev1-root", type=Path, default=DEV1_PRIVATE_DEFAULT)
    parser.add_argument("--dev2-root", type=Path, default=DEV2_PRIVATE_DEFAULT)
    parser.add_argument("--pilot-root", type=Path, default=PILOT_PRIVATE_DEFAULT)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_confirm(args.dev1_root, args.dev2_root, args.pilot_root, args.private_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
