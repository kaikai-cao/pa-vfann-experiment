"""H1.3: deterministic E1 prefix-constraint inference audit.

Reuses the frozen H1.2 environment and its 240 ACL instances. The attack sees
only public paths, stop positions and public E1 parameters. It builds prefix
sum constraints from all three stop regimes and performs deterministic bound
propagation. The true ACL is used only by the final scorer.

No new ACL, no new graph/query, no ILP, no ML, no E2, no defense.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
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

# Fixed descriptive gate, recorded in manifest before interpretation.
NEW_MEMBER_THRESHOLD = 5
GAIN_FRACTION_THRESHOLD = 0.50
RELATIVE_RECALL_GAIN_THRESHOLD = 0.10
MAX_PROPAGATION_ROUNDS = 2000

VARIANTS = ("terminal_only", "prefix_no_size", "prefix_with_size")

ACL_COLUMNS = [
    "acl_id", "policy_type", "selectivity_pct", "variant",
    "authorized_docs", "total_queries", "informative_queries",
    "tau_eq_m", "tau_eq_B", "constraints_count",
    "predicted_authorized", "predicted_unauthorized",
    "auth_tp", "auth_fp", "auth_precision", "auth_recall",
    "unauth_tp", "unauth_fp", "unauth_precision", "unauth_recall",
    "new_authorized_nodes", "new_authorized_tp", "new_unauthorized_nodes",
    "determined_fraction", "relative_recall_gain",
]

SUMMARY_COLUMNS = [
    "policy_type", "selectivity_pct", "variant", "acl_instances",
    "mean_terminal_recall", "mean_variant_recall", "mean_relative_recall_gain",
    "mean_new_authorized_nodes", "new_authorized_acl_fraction",
    "mean_new_unauthorized_nodes", "mean_determined_fraction",
    "mean_auth_precision", "mean_unauth_precision", "mean_unauth_recall",
]


# --------------------------------------------------------------------------- #
# Public constraints and deterministic propagation                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PrefixConstraint:
    """Public prefix sum bound: lower <= sum_{v in nodes} a_v <= upper."""

    nodes: np.ndarray
    lower: int
    upper: int
    source: str


def public_constraints(
    paths: Sequence[Sequence[int]],
    taus: Sequence[int],
    n: int,
    k: int = TOP_K,
    min_visits: int = MIN_VISITS,
    max_budget: int = MAX_BUDGET,
) -> tuple[list[PrefixConstraint], list[int]]:
    """Build constraints from public paths and stop positions only."""
    if len(paths) != len(taus):
        raise ValueError("paths and taus must have the same length")
    constraints: list[PrefixConstraint] = []
    terminal_nodes: list[int] = []
    for q, (path, tau_raw) in enumerate(zip(paths, taus)):
        tau = int(tau_raw)
        path_np = np.asarray(path, dtype=np.int64)
        if tau == min_visits:
            constraints.append(
                PrefixConstraint(path_np[:min_visits], k, int(n), f"q{q}:tau_eq_m")
            )
        elif min_visits < tau < max_budget:
            constraints.append(
                PrefixConstraint(path_np[: tau - 1], k - 1, k - 1, f"q{q}:prefix_eq")
            )
            node = int(path_np[tau - 1])
            constraints.append(
                PrefixConstraint(np.asarray([node], dtype=np.int64), 1, 1, f"q{q}:terminal")
            )
            terminal_nodes.append(node)
        elif tau >= max_budget:
            constraints.append(
                PrefixConstraint(path_np[: max_budget - 1], 0, k - 1, f"q{q}:tau_eq_B")
            )
        else:
            raise ValueError(f"invalid stop position tau={tau} for query {q}")
    return constraints, terminal_nodes


def infer_from_constraints(
    n: int,
    constraints: Sequence[PrefixConstraint],
    authorized_count: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """ATTACK: deterministic bound propagation, no ACL and no result IDs.

    Returns ``(must_authorized, must_unauthorized)`` boolean arrays over nodes.
    """
    n = int(n)
    if n <= 0:
        raise ValueError("n must be positive")
    lower = np.zeros(n, dtype=np.uint8)
    upper = np.ones(n, dtype=np.uint8)

    all_constraints = list(constraints)
    if authorized_count is not None:
        m = int(authorized_count)
        if m < 0 or m > n:
            raise ValueError("authorized_count must satisfy 0 <= M <= N")
        all_constraints.append(
            PrefixConstraint(np.arange(n, dtype=np.int64), m, m, "aux:acl_size")
        )

    for _ in range(MAX_PROPAGATION_ROUNDS):
        changed = False
        for constraint in all_constraints:
            nodes = constraint.nodes
            if nodes.size == 0:
                if constraint.lower > 0 or constraint.upper < 0:
                    raise RuntimeError("empty prefix constraint is inconsistent")
                continue
            if constraint.lower < 0 or constraint.upper > n or constraint.lower > constraint.upper:
                raise ValueError("invalid constraint bounds")
            k_min = int(lower[nodes].sum())
            k_max = int(upper[nodes].sum())
            if k_min > constraint.upper or k_max < constraint.lower:
                raise RuntimeError(
                    f"inconsistent public constraints at {constraint.source}: "
                    f"k_min={k_min}, k_max={k_max}, bounds=({constraint.lower},{constraint.upper})"
                )
            unknown = (lower[nodes] == 0) & (upper[nodes] == 1)
            # Lower bound: if even omitting one unknown cannot reach L, all unknowns are 1.
            if k_max == constraint.lower and unknown.any():
                lower[nodes[unknown]] = 1
                changed = True
                k_min = int(lower[nodes].sum())
                k_max = int(upper[nodes].sum())
            unknown = (lower[nodes] == 0) & (upper[nodes] == 1)
            # Upper bound: if known-1 already reaches U, all unknowns are 0.
            if k_min == constraint.upper and unknown.any():
                upper[nodes[unknown]] = 0
                changed = True
        if not changed:
            break
    else:
        raise RuntimeError("constraint propagation did not converge")

    if np.any((lower == 1) & (upper == 0)):
        raise RuntimeError("contradictory node labels after propagation")
    return lower.astype(bool), ~upper.astype(bool)


# --------------------------------------------------------------------------- #
# Evaluation only: the ACL is consumed here, never by the attack              #
# --------------------------------------------------------------------------- #
def assert_sound_labels(
    predicted_auth: set[int],
    predicted_unauth: set[int],
    true_auth: set[int],
    n: int,
) -> None:
    if predicted_auth & predicted_unauth:
        raise RuntimeError("a node received both authorized and unauthorized labels")
    if not predicted_auth <= true_auth:
        raise RuntimeError(f"false authorized labels: {sorted(predicted_auth - true_auth)[:5]}")
    if predicted_unauth & true_auth:
        raise RuntimeError(f"false unauthorized labels: {sorted(predicted_unauth & true_auth)[:5]}")
    if (predicted_auth | predicted_unauth) and not (predicted_auth | predicted_unauth) <= set(range(n)):
        raise RuntimeError("predicted node id outside 0..N-1")


def score_labels(
    predicted_auth: set[int],
    predicted_unauth: set[int],
    true_auth: set[int],
    n: int,
    terminal_auth: set[int] | None = None,
) -> dict[str, object]:
    """Score attack output; the true ACL is available only to this function."""
    assert_sound_labels(predicted_auth, predicted_unauth, true_auth, n)
    m = len(true_auth)
    auth_tp = len(predicted_auth & true_auth)
    auth_fp = len(predicted_auth - true_auth)
    unauth_tp = len(predicted_unauth - true_auth)
    unauth_fp = len(predicted_unauth & true_auth)
    n_unauth = n - m
    terminal = set() if terminal_auth is None else set(terminal_auth)
    new_auth = predicted_auth - terminal
    new_unauth = predicted_unauth - terminal
    terminal_tp = len(terminal & true_auth)
    return {
        "predicted_authorized": len(predicted_auth),
        "predicted_unauthorized": len(predicted_unauth),
        "auth_tp": auth_tp,
        "auth_fp": auth_fp,
        "auth_precision": (auth_tp / len(predicted_auth)) if predicted_auth else None,
        "auth_recall": (auth_tp / m) if m else None,
        "unauth_tp": unauth_tp,
        "unauth_fp": unauth_fp,
        "unauth_precision": (unauth_tp / len(predicted_unauth)) if predicted_unauth else None,
        "unauth_recall": (unauth_tp / n_unauth) if n_unauth else None,
        "new_authorized_nodes": len(new_auth),
        "new_authorized_tp": len(new_auth & true_auth),
        "new_unauthorized_nodes": len(new_unauth),
        "determined_fraction": (len(predicted_auth) + len(predicted_unauth)) / float(n),
        "terminal_auth_tp": terminal_tp,
        "terminal_auth_precision": (terminal_tp / len(terminal)) if terminal else None,
        "terminal_auth_recall": (terminal_tp / m) if m else None,
        "terminal_determined_fraction": len(terminal) / float(n),
        "relative_recall_gain": (
            ((auth_tp / m) - (terminal_tp / m)) / (terminal_tp / m)
            if m and terminal_tp else 0.0
        ),
    }


def assess_substantial_gain(summary: pd.DataFrame) -> dict[str, object]:
    """Pre-registered descriptive gate; primary variant excludes ACL-size help."""
    primary = summary[summary["variant"] == "prefix_no_size"]
    winners = primary[
        (primary["mean_new_authorized_nodes"] >= NEW_MEMBER_THRESHOLD)
        & (primary["new_authorized_acl_fraction"] >= GAIN_FRACTION_THRESHOLD)
        & (primary["mean_relative_recall_gain"] >= RELATIVE_RECALL_GAIN_THRESHOLD)
    ]
    reached = len(winners) > 0
    return {
        "substantial_gain_reached": reached,
        "decision": (
            "CANDIDATE_FOR_STRONGER_CONSTRAINT_SOLVER"
            if reached else "STOP_NO_ESCALATION"
        ),
        "winner_cells": [
            f"{row.get('policy_type', 'unknown')}/{int(row.get('selectivity_pct', 0))}%"
            for _, row in winners.iterrows()
        ],
        "thresholds": {
            "mean_new_authorized_nodes": NEW_MEMBER_THRESHOLD,
            "new_authorized_acl_fraction": GAIN_FRACTION_THRESHOLD,
            "mean_relative_recall_gain": RELATIVE_RECALL_GAIN_THRESHOLD,
        },
    }


def assess_label_determination(summary: pd.DataFrame) -> dict[str, object]:
    """Secondary observation: negative-label gain, outside the escalation gate."""
    primary = summary[summary["variant"] == "prefix_no_size"]
    rows: list[dict[str, object]] = []
    for (policy, pct), g in primary.groupby(["policy_type", "selectivity_pct"], sort=False):
        terminal = summary[
            (summary["variant"] == "terminal_only")
            & (summary["policy_type"] == policy)
            & (summary["selectivity_pct"] == pct)
        ]
        if terminal.empty or g.empty:
            continue
        gain = float(g["mean_determined_fraction"].iloc[0]) - float(
            terminal["mean_determined_fraction"].iloc[0]
        )
        rows.append(
            {
                "policy_type": str(policy),
                "selectivity_pct": int(pct),
                "determined_fraction_gain": gain,
                "mean_new_unauthorized_nodes": float(g["mean_new_unauthorized_nodes"].iloc[0]),
                "mean_unauth_precision": (
                    float(g["mean_unauth_precision"].iloc[0])
                    if pd.notna(g["mean_unauth_precision"].iloc[0]) else None
                ),
            }
        )
    return {
        "cells": rows,
        "max_determined_fraction_gain": max(
            (float(r["determined_fraction_gain"]) for r in rows), default=0.0
        ),
        "in_escalation_gate": False,
        "interpretation": (
            "Extra determined labels are unauthorized (negative) labels; this is "
            "not counted as recovering additional authorized members."
        ),
    }


# --------------------------------------------------------------------------- #
# Experiment driver                                                            #
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


def run_experiment(
    config_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    cfg = load_config(config_path or default_config_path())
    out = Path(output_dir) if output_dir is not None else ROOT / "results" / "h1_3_prefix_constraint"
    out.mkdir(parents=True, exist_ok=True)

    h1_2_dir = ROOT / "results" / "h1_2_acl_generalization"
    h1_2_manifest = json.loads((h1_2_dir / "manifest.json").read_text(encoding="utf-8"))
    h1_2_acl = pd.read_csv(h1_2_dir / "acl_metrics.csv")

    dataset, graph, qdist = prepare(cfg)
    n = dataset.n
    qdist_rows = int(dataset.n_queries)
    k = int(cfg["search"]["top_k"])
    max_budget = max(int(v) for v in cfg["search"]["budgets"])
    min_visits = int(cfg["search"]["initial_budget"])
    sigma = float(cfg["policies"]["clustered_sigma"])
    n_centers = int(cfg["policies"]["clustered_centers"])
    if (n, qdist_rows, k, max_budget, min_visits) != (10000, 200, 10, 1000, 20):
        raise RuntimeError("frozen H1.2 environment mismatch")

    paths = [plan_fixed_trace(qdist[q], graph, max_budget)[0] for q in range(qdist_rows)]
    recomputed_hashes = {
        "vectors_sha256": array_sha256(dataset.vectors),
        "queries_sha256": array_sha256(dataset.query_vectors),
        "qdist_sha256": array_sha256(qdist),
        "graph_sha256": graph_sha256(graph),
        "public_paths_sha256": public_paths_sha256(paths),
        "config_sha256": file_sha256(Path(cfg.path)),
    }
    if recomputed_hashes != h1_2_manifest["environment_hashes"]:
        raise RuntimeError("H1.2 environment hash mismatch; audit aborted")
    if len(h1_2_acl) != 240:
        raise RuntimeError(f"expected 240 H1.2 ACLs, found {len(h1_2_acl)}")

    acl_rows: list[dict[str, object]] = []
    for hrow in h1_2_acl.itertuples(index=False):
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

        bits = [bool(v) for v in policy.mask]
        taus = [
            simulate_e1_stop(path, bits, k, min_visits, max_budget)
            for path in paths
        ]
        tau_m = sum(1 for t in taus if t == min_visits)
        tau_b = sum(1 for t in taus if t >= max_budget)
        informative = sum(1 for t in taus if min_visits < t < max_budget)
        if (tau_m, tau_b, informative) != (
            int(hrow.tau_eq_m), int(hrow.tau_eq_B), int(hrow.informative_queries)
        ):
            raise RuntimeError(f"stop-position aggregate mismatch for {acl_id}")

        constraints, terminal_nodes = public_constraints(
            paths, taus, n, k, min_visits, max_budget
        )
        if len(set(terminal_nodes)) != int(hrow.unique_inferred_nodes):
            raise RuntimeError(f"terminal-only reconstruction mismatch for {acl_id}")
        true_auth = {int(v) for v in np.flatnonzero(bits)}

        for variant in VARIANTS:
            if variant == "terminal_only":
                pred_auth = set(terminal_nodes)
                pred_unauth: set[int] = set()
                constraint_count = 0
            else:
                pred_auth_arr, pred_unauth_arr = infer_from_constraints(
                    n,
                    constraints,
                    authorized_count=(m if variant == "prefix_with_size" else None),
                )
                pred_auth = set(int(v) for v in np.flatnonzero(pred_auth_arr))
                pred_unauth = set(int(v) for v in np.flatnonzero(pred_unauth_arr))
                constraint_count = len(constraints) + (
                    1 if variant == "prefix_with_size" else 0
                )
            score = score_labels(
                pred_auth, pred_unauth, true_auth, n, terminal_auth=set(terminal_nodes)
            )
            acl_rows.append(
                {
                    "acl_id": acl_id,
                    "policy_type": str(hrow.policy_type),
                    "selectivity_pct": int(hrow.selectivity_pct),
                    "variant": variant,
                    "authorized_docs": m,
                    "total_queries": qdist_rows,
                    "informative_queries": informative,
                    "tau_eq_m": tau_m,
                    "tau_eq_B": tau_b,
                    "constraints_count": constraint_count,
                    "predicted_authorized": int(score["predicted_authorized"]),
                    "predicted_unauthorized": int(score["predicted_unauthorized"]),
                    "auth_tp": int(score["auth_tp"]),
                    "auth_fp": int(score["auth_fp"]),
                    "auth_precision": score["auth_precision"],
                    "auth_recall": score["auth_recall"],
                    "unauth_tp": int(score["unauth_tp"]),
                    "unauth_fp": int(score["unauth_fp"]),
                    "unauth_precision": score["unauth_precision"],
                    "unauth_recall": score["unauth_recall"],
                    "new_authorized_nodes": int(score["new_authorized_nodes"]),
                    "new_authorized_tp": int(score["new_authorized_tp"]),
                    "new_unauthorized_nodes": int(score["new_unauthorized_nodes"]),
                    "determined_fraction": float(score["determined_fraction"]),
                    "relative_recall_gain": float(score["relative_recall_gain"]),
                }
            )

    acl_df = pd.DataFrame(acl_rows, columns=ACL_COLUMNS)
    acl_csv = out / "acl_metrics.csv"
    acl_df.to_csv(acl_csv, index=False)

    summary_rows: list[dict[str, object]] = []
    for (policy, pct, variant), g in acl_df.groupby(
        ["policy_type", "selectivity_pct", "variant"], sort=False
    ):
        terminal = acl_df[
            (acl_df["policy_type"] == policy)
            & (acl_df["selectivity_pct"] == pct)
            & (acl_df["variant"] == "terminal_only")
        ]
        summary_rows.append(
            {
                "policy_type": str(policy),
                "selectivity_pct": int(pct),
                "variant": str(variant),
                "acl_instances": int(len(g)),
                "mean_terminal_recall": float(terminal["auth_recall"].mean()),
                "mean_variant_recall": float(g["auth_recall"].mean()),
                "mean_relative_recall_gain": float(g["relative_recall_gain"].mean()),
                "mean_new_authorized_nodes": float(g["new_authorized_nodes"].mean()),
                "new_authorized_acl_fraction": float(
                    (g["new_authorized_nodes"] > 0).mean()
                ),
                "mean_new_unauthorized_nodes": float(g["new_unauthorized_nodes"].mean()),
                "mean_determined_fraction": float(g["determined_fraction"].mean()),
                "mean_auth_precision": float(g["auth_precision"].mean()),
                "mean_unauth_precision": float(g["unauth_precision"].dropna().mean())
                if g["unauth_precision"].notna().any() else None,
                "mean_unauth_recall": float(g["unauth_recall"].mean()),
            }
        )
    summary_df = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    summary_csv = out / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    decision = assess_substantial_gain(summary_df)
    manifest = {
        "experiment": "H1_3_PREFIX_CONSTRAINT_INFERENCE",
        "baseline_commit": git_head(),
        "h1_2_baseline_commit": h1_2_manifest.get("baseline_commit"),
        "reused_h1_2": {
            "acl_metrics_sha256": file_sha256(h1_2_dir / "acl_metrics.csv"),
            "manifest_sha256": file_sha256(h1_2_dir / "manifest.json"),
            "acl_instances": 240,
            "queries": 200,
            "new_acl_instances": 0,
        },
        "environment_hashes": recomputed_hashes,
        "attack": {
            "inputs": "public paths, stop positions, E1 parameters; optional aggregate M",
            "acl_or_result_ids_to_attack": False,
            "method": "deterministic prefix bound propagation",
            "ilp_or_ml": False,
            "variants": list(VARIANTS),
        },
        "pre_registered_gate": decision,
        "secondary_label_determination": assess_label_determination(summary_df),
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
        f"[h1.3] reused 240 H1.2 ACLs; rows={len(acl_df)} summary={len(summary_df)}",
        flush=True,
    )
    print(f"[h1.3] gate: {decision['decision']} winners={decision['winner_cells']}", flush=True)
    return {
        "acl_rows": acl_rows,
        "summary_rows": summary_rows,
        "manifest": manifest,
        "paths": {"acl_metrics": acl_csv, "summary": summary_csv, "manifest": manifest_path},
    }


def main() -> None:
    result = run_experiment()
    for row in result["summary_rows"]:
        print(
            f"[h1.3] {row['policy_type']:>9}/{row['selectivity_pct']:>2}% "
            f"{row['variant']:>16} recall={row['mean_variant_recall']:.4f} "
            f"new_auth={row['mean_new_authorized_nodes']:.2f} "
            f"determined={row['mean_determined_fraction']:.4f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
