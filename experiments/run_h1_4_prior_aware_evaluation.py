"""H1.4: prior-aware evaluation of H1.3 negative-member inference.

The question is not whether H1.3's unauthorized labels are sound by
construction (they are), but how much information they add beyond:

  B0  all-negative prior,
  B1  matched-budget uniform random guessing, and
  B2  public-path visit frequency (no stop positions, no ACL, no result ID).

The H1.3 attack output is rebuilt from H1.2's 240 frozen ACL instances and
the fixed public paths. The true ACL is used only by the scorer.

No new ACL, no new graph/query, no rerun of H1.2/H1.3 drivers, no ILP/ML,
no E2, no defense, no extra samples.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from pa_vfann.config import default_config_path, load_config  # noqa: E402
from pa_vfann.search_common import plan_fixed_trace  # noqa: E402

from experiments.exp_common import prepare  # noqa: E402
from experiments.run_h1_2_acl_generalization import (  # noqa: E402
    MIN_VISITS,
    MAX_BUDGET,
    TOP_K,
    array_sha256,
    file_sha256,
    graph_sha256,
    make_acl_dataset_and_policy,
    mask_sha256,
    public_paths_sha256,
    simulate_e1_stop,
)
from experiments.run_h1_3_prefix_constraint_inference import (  # noqa: E402
    infer_from_constraints,
    public_constraints,
)

BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20261125
BOOTSTRAP_NAMESPACE = 0x48314254  # H1BT
B1_SEED_NAMESPACE = 0x42314031  # B1@1
PRIMARY_CELL = ("random", 1)
BA_GAIN_THRESHOLD = 0.05
CI_LOWER_THRESHOLD = 0.0

METHODS = ("h1_3_prefix", "b0_all_negative", "b1_matched_random", "b2_path_frequency")

ACL_COLUMNS = [
    "acl_id", "policy_type", "selectivity_pct", "method",
    "n_nodes", "authorized_docs", "unauthorized_docs", "predicted_L",
    "tp", "fp", "fn", "tn",
    "precision", "recall", "fpr", "specificity", "balanced_accuracy",
    "h1_3_budget_expected_fp_random", "h1_3_budget_p_zero_fp_random",
    "delta_ba_vs_b2", "delta_ba_vs_b1",
    "delta_recall_vs_b2", "delta_fpr_vs_b2",
]

SUMMARY_COLUMNS = [
    "policy_type", "selectivity_pct", "method", "acl_instances",
    "mean_predicted_L", "mean_tp", "mean_fp",
    "mean_precision", "mean_recall", "mean_fpr", "mean_specificity",
    "mean_balanced_accuracy",
    "delta_ba_vs_b2_mean", "delta_ba_vs_b2_ci_low", "delta_ba_vs_b2_ci_high",
    "delta_ba_vs_b1_mean", "delta_ba_vs_b1_ci_low", "delta_ba_vs_b1_ci_high",
    "b1_analytic_expected_fp", "b1_analytic_p_zero_fp",
    "h1_3_fp_total", "bootstrap_reps",
]


# --------------------------------------------------------------------------- #
# Deterministic helper construction (no ACL inputs)                           #
# --------------------------------------------------------------------------- #
def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def path_frequency_order(
    paths: Sequence[Sequence[int]], n: int
) -> tuple[np.ndarray, np.ndarray]:
    """B2 ranking: public-path visit count, ties broken by ascending node ID.

    Only the complete public paths are consumed: no stop position, no ACL,
    no result ID, no policy parameter.
    """
    n = int(n)
    if n <= 0:
        raise ValueError("n must be positive")
    counts = np.zeros(n, dtype=np.int64)
    for q, path in enumerate(paths):
        arr = np.asarray(path, dtype=np.int64)
        if arr.size == 0:
            raise ValueError(f"empty public path at query {q}")
        if np.any(arr < 0) or np.any(arr >= n):
            raise ValueError(f"node id outside 0..N-1 in public path {q}")
        np.add.at(counts, arr, 1)
    node_ids = np.arange(n, dtype=np.int64)
    order = np.lexsort((node_ids, -counts))
    if order.size != n or len(set(int(v) for v in order)) != n:
        raise RuntimeError("B2 ranking is not a permutation of all nodes")
    return order, counts


def b2_predict(order: Sequence[int], budget: int) -> np.ndarray:
    """Select the first L nodes of the ACL-independent public-path ranking."""
    budget = int(budget)
    arr = np.asarray(order, dtype=np.int64)
    if budget < 0 or budget > arr.size:
        raise ValueError("B2 budget must satisfy 0 <= L <= N")
    return arr[:budget].copy()


def b1_seed(acl_id: str) -> int:
    """Stable per-ACL seed for the matched-budget uniform random baseline."""
    if not acl_id:
        raise ValueError("acl_id must be non-empty")
    digest = hashlib.sha256(f"H1.4:B1:{acl_id}".encode("utf-8")).digest()
    seq = np.random.SeedSequence(
        [B1_SEED_NAMESPACE, int.from_bytes(digest[:8], byteorder="big")]
    )
    return int(seq.generate_state(1, dtype=np.uint64)[0])


def b1_predict(n: int, budget: int, seed: int) -> np.ndarray:
    """B1: uniform random sample of L distinct nodes, without replacement."""
    n = int(n)
    budget = int(budget)
    if n <= 0 or budget < 0 or budget > n:
        raise ValueError("B1 requires 0 <= L <= N and N > 0")
    rng = np.random.default_rng(int(seed))
    return rng.choice(n, size=budget, replace=False)


def hypergeometric_expected_fp(n: int, m: int, budget: int) -> float:
    """Expected FP of a uniform random L-subset: E[FP] = L*M/N."""
    n, m, budget = int(n), int(m), int(budget)
    if n <= 0 or not 0 <= m <= n or not 0 <= budget <= n:
        raise ValueError("hypergeometric parameters out of range")
    return float(budget) * float(m) / float(n)


def hypergeometric_zero_fp_probability(n: int, m: int, budget: int) -> float:
    """P(FP=0) = C(N-M, L) / C(N, L), computed in log space."""
    n, m, budget = int(n), int(m), int(budget)
    if n <= 0 or not 0 <= m <= n or not 0 <= budget <= n:
        raise ValueError("hypergeometric parameters out of range")
    if budget == 0:
        return 1.0
    if budget > n - m:
        return 0.0

    def log_binom(a: int, b: int) -> float:
        return (
            math.lgamma(a + 1)
            - math.lgamma(b + 1)
            - math.lgamma(a - b + 1)
        )

    log_p = log_binom(n - m, budget) - log_binom(n, budget)
    return float(math.exp(log_p))


# --------------------------------------------------------------------------- #
# Independent scorer: "unauthorized" is the positive class                    #
# --------------------------------------------------------------------------- #
def score_negative_labels(
    predicted_nodes: Sequence[int], true_authorized: set[int], n: int
) -> dict[str, object]:
    """Score a predicted unauthorized set; the ACL is consumed only here."""
    n = int(n)
    if n <= 0:
        raise ValueError("n must be positive")
    arr = np.asarray(predicted_nodes, dtype=np.int64)
    if arr.size and (np.any(arr < 0) or np.any(arr >= n)):
        raise ValueError("predicted node id outside 0..N-1")
    nodes = {int(v) for v in arr}
    if len(nodes) != arr.size:
        raise ValueError("predicted nodes must be distinct")
    auth = {int(v) for v in true_authorized}
    if not auth <= set(range(n)) or len(auth) >= n:
        raise ValueError("true authorized set must be a proper subset of nodes")

    m = len(auth)
    n_unauth = n - m
    pred_count = len(nodes)
    tp = len(nodes - auth)
    fp = len(nodes & auth)
    fn = n_unauth - tp
    tn = m - fp
    if tp + fp != pred_count or tp + fn != n_unauth or fp + tn != m:
        raise RuntimeError("confusion matrix partition invariant failed")

    precision = (tp / pred_count) if pred_count else None
    recall = (tp / n_unauth) if n_unauth else None
    fpr = (fp / m) if m else None
    specificity = (tn / m) if m else None
    balanced = (
        (float(recall) + float(specificity)) / 2.0
        if recall is not None and specificity is not None else None
    )
    return {
        "predicted_L": pred_count,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "fpr": fpr,
        "specificity": specificity,
        "balanced_accuracy": balanced,
    }


# --------------------------------------------------------------------------- #
# ACL-level paired bootstrap                                                   #
# --------------------------------------------------------------------------- #
def cell_bootstrap_seed(policy_type: str, selectivity_pct: int) -> int:
    seq = np.random.SeedSequence(
        [BOOTSTRAP_SEED, int(selectivity_pct), BOOTSTRAP_NAMESPACE,
         int.from_bytes(policy_type.encode("ascii"), byteorder="big")]
    )
    return int(seq.generate_state(1, dtype=np.uint64)[0])


def paired_bootstrap_mean_ci(
    diffs: Sequence[float],
    rng: np.random.Generator,
    reps: int = BOOTSTRAP_REPS,
) -> tuple[float, float, float]:
    """Paired ACL-level percentile CI for a per-ACL difference."""
    arr = np.asarray(diffs, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("diffs must be a non-empty one-dimensional sequence")
    if int(reps) <= 0:
        raise ValueError("reps must be positive")
    index = rng.integers(0, arr.size, size=(int(reps), arr.size))
    means = arr[index].mean(axis=1)
    return (
        float(arr.mean()),
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


def assess_upgrade_gate(summary: pd.DataFrame) -> dict[str, object]:
    """Pre-registered decision for the primary cell random/1%."""
    cell = summary[
        (summary["policy_type"] == PRIMARY_CELL[0])
        & (summary["selectivity_pct"] == PRIMARY_CELL[1])
    ].set_index("method")
    required = {"h1_3_prefix", "b1_matched_random", "b2_path_frequency"}
    if not required <= set(cell.index):
        raise RuntimeError("primary cell is missing a required method row")

    attack = cell.loc["h1_3_prefix"]
    b1 = cell.loc["b1_matched_random"]
    b2 = cell.loc["b2_path_frequency"]

    gain_b2 = float(attack["mean_balanced_accuracy"] - b2["mean_balanced_accuracy"])
    gain_b1 = float(attack["mean_balanced_accuracy"] - b1["mean_balanced_accuracy"])
    ci_b2_low = float(attack["delta_ba_vs_b2_ci_low"])
    ci_b1_low = float(attack["delta_ba_vs_b1_ci_low"])
    fp_total = int(attack["h1_3_fp_total"])

    checks = {
        "mean_ba_gain_vs_b2_at_least_0_05": bool(gain_b2 >= BA_GAIN_THRESHOLD),
        "paired_ci_vs_b2_lower_above_0": bool(ci_b2_low > CI_LOWER_THRESHOLD),
        "mean_ba_gain_vs_b1_at_least_0_05": bool(gain_b1 >= BA_GAIN_THRESHOLD),
        "paired_ci_vs_b1_lower_above_0": bool(ci_b1_low > CI_LOWER_THRESHOLD),
        "zero_negative_label_fp": bool(fp_total == 0),
    }
    reached = all(checks.values())
    return {
        "primary_cell": f"{PRIMARY_CELL[0]}/{PRIMARY_CELL[1]}%",
        "checks": checks,
        "mean_ba_gain_vs_b2": gain_b2,
        "paired_ci_vs_b2": [ci_b2_low, float(attack["delta_ba_vs_b2_ci_high"])],
        "mean_ba_gain_vs_b1": gain_b1,
        "paired_ci_vs_b1": [ci_b1_low, float(attack["delta_ba_vs_b1_ci_high"])],
        "h1_3_false_unauthorized_total": fp_total,
        "decision": (
            "CANDIDATE_NEGATIVE_MEMBERSHIP_LEAKAGE" if reached
            else "STOP_NEGATIVE_EXTENSION"
        ),
        "thresholds": {
            "mean_balanced_accuracy_gain": BA_GAIN_THRESHOLD,
            "paired_ci_lower_strictly_above": CI_LOWER_THRESHOLD,
            "bootstrap_reps": BOOTSTRAP_REPS,
            "bootstrap_unit": "acl_instance",
        },
    }


# --------------------------------------------------------------------------- #
# Experiment driver                                                            #
# --------------------------------------------------------------------------- #
def run_experiment(
    config_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    cfg = load_config(config_path or default_config_path())
    out = Path(output_dir) if output_dir is not None else ROOT / "results" / "h1_4_prior_aware"
    out.mkdir(parents=True, exist_ok=True)

    h12_dir = ROOT / "results" / "h1_2_acl_generalization"
    h13_dir = ROOT / "results" / "h1_3_prefix_constraint"
    h12_manifest = json.loads((h12_dir / "manifest.json").read_text(encoding="utf-8"))
    h13_manifest = json.loads((h13_dir / "manifest.json").read_text(encoding="utf-8"))
    h12_acl = pd.read_csv(h12_dir / "acl_metrics.csv")
    h13_acl = pd.read_csv(h13_dir / "acl_metrics.csv")
    if file_sha256(h12_dir / "acl_metrics.csv") != h13_manifest["reused_h1_2"]["acl_metrics_sha256"]:
        raise RuntimeError("H1.2 ACL CSV hash disagrees with H1.3 manifest")
    if file_sha256(h13_dir / "acl_metrics.csv") != h13_manifest["output_files"]["acl_metrics.csv"]["sha256"]:
        raise RuntimeError("H1.3 ACL CSV hash disagrees with H1.3 manifest")
    if len(h12_acl) != 240 or len(h13_acl) != 720:
        raise RuntimeError("unexpected H1.2/H1.3 row counts")
    if set(inspect.signature(infer_from_constraints).parameters) != {
        "n", "constraints", "authorized_count"
    }:
        raise RuntimeError("H1.3 attack signature changed: ACL may leak into attack")

    dataset, graph, qdist = prepare(cfg)
    n = int(dataset.n)
    n_queries = int(dataset.n_queries)
    k = int(cfg["search"]["top_k"])
    max_budget = max(int(v) for v in cfg["search"]["budgets"])
    min_visits = int(cfg["search"]["initial_budget"])
    sigma = float(cfg["policies"]["clustered_sigma"])
    n_centers = int(cfg["policies"]["clustered_centers"])
    if (n, n_queries, k, max_budget, min_visits) != (10000, 200, 10, 1000, 20):
        raise RuntimeError("frozen H1.2 environment mismatch")

    paths = [plan_fixed_trace(qdist[q], graph, max_budget)[0] for q in range(n_queries)]
    recomputed_hashes = {
        "vectors_sha256": array_sha256(dataset.vectors),
        "queries_sha256": array_sha256(dataset.query_vectors),
        "qdist_sha256": array_sha256(qdist),
        "graph_sha256": graph_sha256(graph),
        "public_paths_sha256": public_paths_sha256(paths),
        "config_sha256": file_sha256(Path(cfg.path)),
    }
    if recomputed_hashes != h12_manifest["environment_hashes"]:
        raise RuntimeError("H1.2 environment hash mismatch; audit aborted")
    if recomputed_hashes != h13_manifest["environment_hashes"]:
        raise RuntimeError("H1.3 environment hash mismatch; audit aborted")

    # B2 is built once from the public paths, before any ACL is touched.
    path_order, path_counts = path_frequency_order(paths, n)
    path_order_hash = array_sha256(path_order)
    path_counts_hash = array_sha256(path_counts)

    h13_index = h13_acl.set_index(["acl_id", "variant"])
    rows: list[dict[str, object]] = []
    for hrow in h12_acl.itertuples(index=False):
        acl_id = str(hrow.acl_id)
        _, policy = make_acl_dataset_and_policy(
            dataset,
            str(hrow.policy_type),
            float(hrow.selectivity_pct) / 100.0,
            sigma,
            n_centers,
            int(hrow.acl_seed),
        )
        if mask_sha256(policy.mask) != str(hrow.mask_sha256):
            raise RuntimeError(f"ACL mask reconstruction failed for {acl_id}")
        m = int(policy.actual_count)
        if m != int(hrow.authorized_docs):
            raise RuntimeError(f"ACL cardinality mismatch for {acl_id}")
        true_auth = {int(v) for v in np.flatnonzero(np.asarray(policy.mask, dtype=bool))}
        bits = [bool(v) for v in policy.mask]

        taus = [simulate_e1_stop(path, bits, k, min_visits, max_budget) for path in paths]
        if (
            sum(1 for t in taus if t == min_visits),
            sum(1 for t in taus if t >= max_budget),
            sum(1 for t in taus if min_visits < t < max_budget),
        ) != (int(hrow.tau_eq_m), int(hrow.tau_eq_B), int(hrow.informative_queries)):
            raise RuntimeError(f"stop-position aggregate mismatch for {acl_id}")

        constraints, terminal_nodes = public_constraints(
            paths, taus, n, k, min_visits, max_budget
        )
        _, pred_unauth_arr = infer_from_constraints(n, constraints)
        pred_unauth = set(int(v) for v in np.flatnonzero(pred_unauth_arr))
        terminal = set(int(v) for v in terminal_nodes)

        # Cross-check the rebuilt attack against the frozen H1.3 output.
        key = (acl_id, "prefix_no_size")
        if key not in h13_index.index:
            raise RuntimeError(f"missing H1.3 prefix_no_size row for {acl_id}")
        h13_row = h13_index.loc[key]
        if int(h13_row["predicted_unauthorized"]) != len(pred_unauth):
            raise RuntimeError(f"H1.3 predicted-unauthorized mismatch for {acl_id}")
        if int(h13_row["unauth_tp"]) != len(pred_unauth - true_auth):
            raise RuntimeError(f"H1.3 unauth TP mismatch for {acl_id}")
        if int(h13_row["unauth_fp"]) != len(pred_unauth & true_auth):
            raise RuntimeError(f"H1.3 unauth FP mismatch for {acl_id}")
        expected_determined = (len(pred_unauth) + len(terminal)) / float(n)
        if abs(float(h13_row["determined_fraction"]) - expected_determined) > 1e-12:
            raise RuntimeError(f"H1.3 determined-fraction mismatch for {acl_id}")

        l_budget = len(pred_unauth)
        exp_fp = hypergeometric_expected_fp(n, m, l_budget)
        p_zero_fp = hypergeometric_zero_fp_probability(n, m, l_budget)
        predictions = {
            "h1_3_prefix": np.asarray(sorted(pred_unauth), dtype=np.int64),
            "b0_all_negative": np.arange(n, dtype=np.int64),
            "b1_matched_random": b1_predict(n, l_budget, b1_seed(acl_id)),
            "b2_path_frequency": b2_predict(path_order, l_budget),
        }
        for method, pred in predictions.items():
            score = score_negative_labels(pred, true_auth, n)
            rows.append(
                {
                    "acl_id": acl_id,
                    "policy_type": str(hrow.policy_type),
                    "selectivity_pct": int(hrow.selectivity_pct),
                    "method": method,
                    "n_nodes": n,
                    "authorized_docs": m,
                    "unauthorized_docs": n - m,
                    "predicted_L": int(score["predicted_L"]),
                    "tp": int(score["tp"]),
                    "fp": int(score["fp"]),
                    "fn": int(score["fn"]),
                    "tn": int(score["tn"]),
                    "precision": score["precision"],
                    "recall": score["recall"],
                    "fpr": score["fpr"],
                    "specificity": score["specificity"],
                    "balanced_accuracy": score["balanced_accuracy"],
                    "h1_3_budget_expected_fp_random": exp_fp,
                    "h1_3_budget_p_zero_fp_random": p_zero_fp,
                }
            )

    acl_df = pd.DataFrame(rows, columns=ACL_COLUMNS)
    wide = acl_df.pivot(index="acl_id", columns="method", values="balanced_accuracy")
    recall_wide = acl_df.pivot(index="acl_id", columns="method", values="recall")
    fpr_wide = acl_df.pivot(index="acl_id", columns="method", values="fpr")
    if wide.shape[0] != 240 or set(wide.columns) != set(METHODS):
        raise RuntimeError("per-ACL method pivot is incomplete")

    acl_df["delta_ba_vs_b2"] = [
        float(wide.loc[a, method] - wide.loc[a, "b2_path_frequency"])
        for a, method in zip(acl_df["acl_id"], acl_df["method"])
    ]
    acl_df["delta_ba_vs_b1"] = [
        float(wide.loc[a, method] - wide.loc[a, "b1_matched_random"])
        for a, method in zip(acl_df["acl_id"], acl_df["method"])
    ]
    acl_df["delta_recall_vs_b2"] = [
        float(recall_wide.loc[a, method] - recall_wide.loc[a, "b2_path_frequency"])
        for a, method in zip(acl_df["acl_id"], acl_df["method"])
    ]
    acl_df["delta_fpr_vs_b2"] = [
        float(fpr_wide.loc[a, method] - fpr_wide.loc[a, "b2_path_frequency"])
        for a, method in zip(acl_df["acl_id"], acl_df["method"])
    ]

    acl_csv = out / "acl_metrics.csv"
    acl_df.to_csv(acl_csv, index=False)

    summary_rows: list[dict[str, object]] = []
    for (policy, pct), cell in acl_df.groupby(["policy_type", "selectivity_pct"], sort=False):
        cell_seed = cell_bootstrap_seed(str(policy), int(pct))
        # One independent ACL-level paired bootstrap per comparison index.
        boot_rngs = [
            np.random.default_rng(
                np.random.SeedSequence([cell_seed, idx, BOOTSTRAP_NAMESPACE])
            )
            for idx in range(2)
        ]
        for method in METHODS:
            g = cell[cell["method"] == method]
            if len(g) != 30:
                raise RuntimeError(f"cell {policy}/{pct}/{method} has {len(g)} ACLs")
            d_b2 = paired_bootstrap_mean_ci(
                g["delta_ba_vs_b2"].to_numpy(dtype=float), boot_rngs[0]
            )
            d_b1 = paired_bootstrap_mean_ci(
                g["delta_ba_vs_b1"].to_numpy(dtype=float), boot_rngs[1]
            )
            attack_fp = int(
                cell[(cell["method"] == "h1_3_prefix")]["fp"].sum()
            )
            summary_rows.append(
                {
                    "policy_type": str(policy),
                    "selectivity_pct": int(pct),
                    "method": method,
                    "acl_instances": int(len(g)),
                    "mean_predicted_L": float(g["predicted_L"].mean()),
                    "mean_tp": float(g["tp"].mean()),
                    "mean_fp": float(g["fp"].mean()),
                    "mean_precision": float(g["precision"].dropna().mean())
                    if g["precision"].notna().any() else None,
                    "mean_recall": float(g["recall"].mean()),
                    "mean_fpr": float(g["fpr"].mean()),
                    "mean_specificity": float(g["specificity"].mean()),
                    "mean_balanced_accuracy": float(g["balanced_accuracy"].mean()),
                    "delta_ba_vs_b2_mean": d_b2[0],
                    "delta_ba_vs_b2_ci_low": d_b2[1],
                    "delta_ba_vs_b2_ci_high": d_b2[2],
                    "delta_ba_vs_b1_mean": d_b1[0],
                    "delta_ba_vs_b1_ci_low": d_b1[1],
                    "delta_ba_vs_b1_ci_high": d_b1[2],
                    "b1_analytic_expected_fp": float(g["h1_3_budget_expected_fp_random"].mean()),
                    "b1_analytic_p_zero_fp": float(g["h1_3_budget_p_zero_fp_random"].mean()),
                    "h1_3_fp_total": attack_fp,
                    "bootstrap_reps": BOOTSTRAP_REPS,
                }
            )

    summary_df = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    summary_csv = out / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    decision = assess_upgrade_gate(summary_df)
    manifest = {
        "experiment": "H1_4_PRIOR_AWARE_NEGATIVE_LEAKAGE",
        "baseline_commit": git_head(),
        "reused_inputs": {
            "h1_2_manifest_sha256": file_sha256(h12_dir / "manifest.json"),
            "h1_2_acl_metrics_sha256": file_sha256(h12_dir / "acl_metrics.csv"),
            "h1_3_manifest_sha256": file_sha256(h13_dir / "manifest.json"),
            "h1_3_acl_metrics_sha256": file_sha256(h13_dir / "acl_metrics.csv"),
            "acl_instances": 240,
            "queries": 200,
            "new_acl_instances": 0,
            "attack_output_rebuilt_not_reused": True,
            "h1_3_cross_check": "per-ACL predicted_unauthorized, unauth TP/FP and determined_fraction",
        },
        "environment_hashes": recomputed_hashes,
        "public_path_frequency": {
            "inputs": "complete public paths only",
            "uses_stop_positions": False,
            "uses_acl": False,
            "uses_result_ids": False,
            "tie_break": "ascending node ID",
            "order_sha256": path_order_hash,
            "counts_sha256": path_counts_hash,
        },
        "baselines": {
            "b0_all_negative": "predict all N nodes as unauthorized",
            "b1_matched_random": "uniform L-subset without replacement; seeded per ACL",
            "b2_path_frequency": "top-L by public-path visit frequency",
            "b1_analytic": "E[FP]=L*M/N; P(FP=0)=C(N-M,L)/C(N,L)",
        },
        "positive_class": "unauthorized",
        "scoring": {
            "acl_or_result_ids_to_attack": False,
            "true_acl_scope": "independent scorer only",
            "metrics": ["TP", "FP", "FN", "TN", "precision", "recall", "FPR",
                        "specificity", "balanced_accuracy"],
            "ilp_or_ml": False,
        },
        "bootstrap": {
            "unit": "acl_instance",
            "paired": True,
            "replications": BOOTSTRAP_REPS,
            "seed": BOOTSTRAP_SEED,
            "interval": "percentile_95",
            "query_level_bootstrap": False,
        },
        "pre_registered_gate": decision,
        "output_files": {
            "acl_metrics.csv": {"sha256": file_sha256(acl_csv), "rows": len(acl_df)},
            "summary.csv": {"sha256": file_sha256(summary_csv), "rows": len(summary_df)},
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"[h1.4] rows={len(acl_df)} summary={len(summary_df)} "
        f"decision={decision['decision']}",
        flush=True,
    )
    return {
        "acl_rows": rows,
        "summary_rows": summary_rows,
        "manifest": manifest,
        "paths": {"acl_metrics": acl_csv, "summary": summary_csv, "manifest": manifest_path},
    }


def main() -> None:
    result = run_experiment()
    for row in result["summary_rows"]:
        if row["method"] in {"h1_3_prefix", "b1_matched_random", "b2_path_frequency"}:
            print(
                f"[h1.4] {row['policy_type']:>9}/{row['selectivity_pct']:>2}% "
                f"{row['method']:>17} BA={row['mean_balanced_accuracy']:.4f} "
                f"recall={row['mean_recall']:.4f} FPR={row['mean_fpr']:.4f} "
                f"dBA_B2={row['delta_ba_vs_b2_mean']:+.4f}",
                flush=True,
            )


if __name__ == "__main__":
    main()
