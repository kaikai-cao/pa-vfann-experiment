"""H1.1: audit deterministic authorization-member leakage at the E1 stop boundary.

Read-only back-analysis of the frozen EXP-01 ``experiment_results.csv``. No new
experiment is run: the public traversal plan is rebuilt from the frozen config
and verified against each row's ``trace_sha16`` before any leakage is measured.

Architecture boundary (mandatory):
  * ``infer_last_node`` is the ATTACK. It receives only the public path, the
    observed stop position, and public parameters (m, B). It cannot receive an
    ACL mask, policy object, result IDs, or any authorization bit.
  * ``evaluate_inference`` is a SEPARATE evaluator. It is the only place the
    true ACL mask is used, and only to score the attack (never to produce it).

Decision rule from the task package: if any informative inference is not an
authorized node, the audit stops with a non-zero exit status.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pandas as pd

from pa_vfann.config import default_config_path, load_config
from pa_vfann.search_common import plan_fixed_trace
from experiments.exp_common import prepare, policy_for

MIN_VISITS = 20
MAX_BUDGET = 1000
TOP_K = 10
BOOTSTRAP_SEED = 20261125  # reserved for later multi-ACL work; unused here


# --------------------------------------------------------------------------- #
# ATTACK -- public information only. Never pass a mask/policy into this fn.    #
# --------------------------------------------------------------------------- #
def infer_last_node(
    public_path: Sequence[int],
    tau: int,
    min_visits: int = MIN_VISITS,
    max_budget: int = MAX_BUDGET,
) -> int | None:
    """Infer one authorized member from the E1 stop boundary.

    Lemma: if m < tau < B, the node visited at position tau is authorized and
    the preceding tau-1 prefix contains exactly K-1 authorized nodes. At tau=m
    (min-visit floor) or tau=B (budget exhausted) the boundary carries no
    deterministic positive label, so the attack returns None.
    """
    tau = int(tau)
    if tau <= int(min_visits) or tau >= int(max_budget):
        return None
    if tau < 1 or tau > len(public_path):
        return None
    return int(public_path[tau - 1])  # tau is 1-indexed


def prefix_hash(public_path: Sequence[int], tau: int) -> str:
    """Public trace hash: identical formula to exp_common.make_row."""
    return hashlib.sha256(
        ",".join(str(int(v)) for v in public_path[: int(tau)]).encode("ascii")
    ).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# EVALUATOR -- the only consumer of the true ACL. Scoring, not attacking.       #
# --------------------------------------------------------------------------- #
def evaluate_inference(
    public_path: Sequence[int],
    tau: int,
    mask: Sequence[bool],
    inferred: int | None,
    k: int = TOP_K,
) -> dict[str, object]:
    """Score a single attack output using the true ACL (evaluation only)."""
    if inferred is None:
        return {"inferred_authorized": None, "prefix_count": None, "lemma_holds": None}
    bits = [bool(b) for b in mask]
    inferred_authorized = bits[int(inferred)]
    prefix_count = sum(1 for v in public_path[: int(tau) - 1] if bits[int(v)])
    return {
        "inferred_authorized": inferred_authorized,
        "prefix_count": prefix_count,
        "lemma_holds": bool(inferred_authorized and prefix_count == int(k) - 1),
    }


def recompute_stop_position(
    public_path: Sequence[int],
    mask: Sequence[bool],
    k: int = TOP_K,
    min_visits: int = MIN_VISITS,
) -> int:
    """Rebuild E1's stop rule from a reconstructed ACL, to validate the ACL."""
    bits = [bool(b) for b in mask]
    legal = 0
    for position, node in enumerate(public_path, start=1):
        if bits[int(node)]:
            legal += 1
        if position >= int(min_visits) and legal >= int(k):
            return position
    return len(public_path)


# --------------------------------------------------------------------------- #
# Audit driver                                                                 #
# --------------------------------------------------------------------------- #
def load_audit_context() -> dict[str, object]:
    cfg = load_config(default_config_path())
    dataset, graph, qdist = prepare(cfg)
    max_budget = max(int(v) for v in cfg["search"]["budgets"])
    min_visits = int(cfg["search"]["initial_budget"])
    k = int(cfg["search"]["top_k"])
    return {
        "cfg": cfg,
        "dataset": dataset,
        "graph": graph,
        "qdist": qdist,
        "max_budget": max_budget,
        "min_visits": min_visits,
        "k": k,
    }


def run_audit(ctx: dict[str, object]) -> dict[str, object]:
    dataset = ctx["dataset"]
    qdist = ctx["qdist"]
    cfg = ctx["cfg"]
    max_budget = int(ctx["max_budget"])
    min_visits = int(ctx["min_visits"])
    k = int(ctx["k"])
    n = dataset.n

    print("[h1.1] rebuilding public plans ...", flush=True)
    plans = [plan_fixed_trace(qdist[q], ctx["graph"], max_budget) for q in range(dataset.n_queries)]

    df = pd.read_csv(ROOT / "results" / "raw" / "experiment_results.csv")
    e1 = df[
        (df["experiment"] == "selectivity")
        & (df["algorithm"] == "E1_POSTFILTER")
        & (df["budget"] == max_budget)
    ].copy()

    # Phase 1 gate: every row's public path prefix must reproduce trace_sha16.
    hash_failures = 0
    for row in e1.itertuples(index=False):
        if prefix_hash(plans[int(row.query_id)][0], int(row.stop_position)) != row.trace_sha16:
            hash_failures += 1
    if hash_failures:
        raise RuntimeError(
            f"trace_sha16 reconstruction failed for {hash_failures}/{len(e1)} rows; "
            "audit aborted (no data was modified)"
        )
    print(f"[h1.1] phase1 trace hash gate: {len(e1)}/{len(e1)} matched", flush=True)

    sigma = float(cfg["policies"]["clustered_sigma"])
    n_centers = int(cfg["policies"]["clustered_centers"])
    groups: dict[tuple[str, float], dict[str, object]] = {}
    records: list[dict[str, object]] = []
    global_mismatch = 0
    acl_rebuild_failures = 0

    for (policy_type, sel_pct), gdf in e1.groupby(["policy_type", "selectivity_pct"]):
        selectivity = float(sel_pct) / 100.0
        # policy_for reads clustered_centers from the frozen config, identical to
        # the batch runner (run_selectivity.py). Use it directly.
        policy = policy_for(cfg, dataset, str(policy_type), selectivity, sigma)
        mask = policy.mask
        actual = int(mask.sum())

        if int(gdf["actual_authorized_count"].iloc[0]) != actual:
            raise RuntimeError(
                f"ACL cardinality mismatch for {policy_type}/{sel_pct}: "
                f"rebuilt {actual} vs CSV {int(gdf['actual_authorized_count'].iloc[0])}"
            )

        key = (str(policy_type), float(sel_pct))
        bucket: dict[str, object] = {
            "n": actual,
            "N": n,
            "mask": mask,
            "random_baseline": actual / n,
            "total": len(gdf),
            "excluded_m": 0,
            "excluded_B": 0,
            "informative": 0,
            "positive_events": 0,
            "correct_events": 0,
            "inferred_list": [],
            "lemma_ok": 0,
        }

        for row in gdf.itertuples(index=False):
            q = int(row.query_id)
            tau = int(row.stop_position)
            public_path = plans[q][0]

            # Validate the reconstructed ACL against the recorded stopping rule.
            if recompute_stop_position(public_path, mask, k, min_visits) != tau:
                acl_rebuild_failures += 1

            if tau == min_visits:
                bucket["excluded_m"] += 1
                continue
            if tau >= max_budget:
                bucket["excluded_B"] += 1
                continue

            # ATTACK: public path + tau only. No ACL is passed in.
            inferred = infer_last_node(public_path, tau, min_visits, max_budget)
            if inferred is None:
                continue
            # EVALUATION: ACL is used here only, to score the attack.
            verdict = evaluate_inference(public_path, tau, mask, inferred, k)

            bucket["informative"] += 1
            bucket["positive_events"] += 1
            bucket["inferred_list"].append(inferred)
            if verdict["inferred_authorized"]:
                bucket["correct_events"] += 1
            else:
                global_mismatch += 1
            if verdict["lemma_holds"]:
                bucket["lemma_ok"] += 1
            records.append(
                {
                    "policy_type": policy_type,
                    "selectivity_pct": sel_pct,
                    "query_id": q,
                    "tau": tau,
                    "inferred_node": inferred,
                    "inferred_authorized": verdict["inferred_authorized"],
                    "prefix_authorized_count": verdict["prefix_count"],
                    "lemma_holds": verdict["lemma_holds"],
                }
            )
        groups[key] = bucket

    if acl_rebuild_failures:
        raise RuntimeError(
            f"ACL reconstruction check failed for {acl_rebuild_failures}/{len(e1)} rows; "
            "audit aborted (evaluation ACL would be unreliable)"
        )
    if global_mismatch:
        raise RuntimeError(
            f"precision != 1: {global_mismatch} inferred nodes were NOT authorized. "
            "Per task package, stop and reconcile theory/implementation/stop semantics/data alignment."
        )

    summary = []
    for (policy_type, sel_pct), b in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        inferred = list(b["inferred_list"])
        counts = Counter(inferred)
        unique_nodes = set(counts)
        events = int(b["positive_events"])
        acl = int(b["n"])
        group_mask = b["mask"]
        covered = len(unique_nodes & set(int(v) for v in group_mask.nonzero()[0]))
        summary.append(
            {
                "policy_type": policy_type,
                "selectivity_pct": sel_pct,
                "total_queries": int(b["total"]),
                "excluded_tau_eq_m": int(b["excluded_m"]),
                "excluded_tau_eq_B": int(b["excluded_B"]),
                "informative_queries": int(b["informative"]),
                "positive_events": events,
                "unique_inferred_nodes": len(unique_nodes),
                "precision": (int(b["correct_events"]) / events) if events else None,
                "acl_coverage": (covered / acl) if acl else None,
                "repeat_nodes": sum(1 for c in counts.values() if c > 1),
                "repeat_events": sum(c - 1 for c in counts.values() if c > 1),
                "random_baseline": float(b["random_baseline"]),
                "lemma_ok_events": int(b["lemma_ok"]),
                "authorized_docs": acl,
            }
        )
    return {"summary": summary, "records": records, "hash_gate": len(e1)}


def print_report(summary: list[dict[str, object]]) -> None:
    print("\n=== E1 stop-boundary leakage (budget=1000) ===")
    header = (
        "policy | sel% | total | tau=m | tau=B | inform | events | unique | "
        "precision | ACLcov | repeat_nodes | random | lemma_ok"
    )
    print(header)
    for r in summary:
        print(
            f"{r['policy_type']:>9} | {r['selectivity_pct']:>4} | {r['total_queries']:>5} | "
            f"{r['excluded_tau_eq_m']:>5} | {r['excluded_tau_eq_B']:>5} | "
            f"{r['informative_queries']:>6} | {r['positive_events']:>6} | "
            f"{r['unique_inferred_nodes']:>6} | {r['precision']} | "
            f"{r['acl_coverage']:.4f} | {r['repeat_nodes']:>11} | "
            f"{r['random_baseline']:.4f} | {r['lemma_ok_events']:>8}"
        )


def main() -> None:
    ctx = load_audit_context()
    result = run_audit(ctx)
    print_report(result["summary"])
    print(f"\n[_h1.1] precision=1 gate: PASS; rows verified={result['hash_gate']}")


if __name__ == "__main__":
    main()
