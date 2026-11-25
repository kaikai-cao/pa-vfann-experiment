"""PA-VFANN EXP-09 runner: policy-oblivious adaptive stopping.

Subcommands:
  tune      run the T2 grid on the tuning queries, freeze one (m, epsilon)
  confirm   run C0 / T1 / frozen T2 / E1 / E2 on confirmation queries only
  verify    cross-check rebuilt public plans against historical EXP-01 CSV

The confirmation program reads results/tables/exp09_selected_params.json and
does not inspect tuning results, so no repeated tuning on the confirmation set
is possible. No base dataset is regenerated: the frozen config is replayed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pa_vfann.baseline_postfilter import adaptive_postfilter_from_plan  # noqa: E402
from pa_vfann.filter_aware import predicate_aware_search  # noqa: E402
from pa_vfann.metrics import recall_at_k  # noqa: E402
from pa_vfann.search_common import truncate_outcome  # noqa: E402

from experiments.exp09_common import (  # noqa: E402
    BUDGETS, SELECTIVITIES, T1_FRACTIONS, T2_GRID, TOPOLOGIES,
    build_conditions, run_invariance_rows, run_stop_rows, trace_hash, write_rows,
    FIELDS, INV_FIELDS,
)
from experiments.exp_common import cli_config, policy_for, prepare  # noqa: E402

RAW = ROOT / "results" / "raw"
TABLES = ROOT / "results" / "tables"
SELECTED = TABLES / "exp09_selected_params.json"


def _conditions_and_tools(config):
    dataset, graph, qdist = prepare(config)
    conditions, top_k = build_conditions(config, dataset, graph, qdist)
    keys = {}
    for topology in TOPOLOGIES:
        for selectivity in SELECTIVITIES:
            sigma = float(config["policies"]["clustered_sigma"])
            keys[(topology, selectivity)] = policy_for(
                config, dataset, topology, selectivity, sigma
            )
    return dataset, graph, qdist, conditions, top_k, keys


def verify_plans(config) -> None:
    """Rebuilt E3 plans must reproduce the historical EXP-01 trace hashes."""
    dataset, graph, qdist, _, top_k, _ = _conditions_and_tools(config)
    historical = pd.read_csv(RAW / "experiment_results.csv")
    hist = historical[
        (historical["experiment"] == "selectivity")
        & (historical["algorithm"] == "E3_FIXED_TRACE")
        & (historical["budget"].isin(BUDGETS))
    ]
    checked = 0
    mismatches = []
    for row in hist.itertuples(index=False):
        visited = tuple(int(v) for v in __import__("pa_vfann.search_common", fromlist=["plan_fixed_trace"])
                        .plan_fixed_trace(qdist[int(row.query_id)], graph, int(row.budget))[0])
        got = trace_hash(visited)
        checked += 1
        if got != str(row.trace_sha16):
            mismatches.append((row.query_id, row.budget, got, row.trace_sha16))
    print(f"[verify] checked {checked} historical E3 trace hashes, mismatches={len(mismatches)}")
    if mismatches:
        print(mismatches[:5])
        raise SystemExit("plan reproducibility check FAILED")
    (TABLES).mkdir(parents=True, exist_ok=True)
    (TABLES / "exp09_plan_reproducibility.csv").write_text(
        "checked_rows,mismatches\n" + f"{checked},{len(mismatches)}\n", encoding="utf-8"
    )


def tune(config) -> None:
    started = time.time()
    dataset, graph, qdist, conditions, top_k, keys = _conditions_and_tools(config)
    nq = dataset.n_queries
    tuning_ids = list(range(nq // 2))
    print(f"[tune] n_queries={nq} tuning_ids={len(tuning_ids)} conditions={len(conditions)}", flush=True)

    methods = [("C0", "full_budget")]
    methods += [("T1", f) for f in T1_FRACTIONS]
    methods += [("T2", g) for g in T2_GRID]
    rows = run_stop_rows(conditions, qdist, graph, top_k, methods, tuning_ids, "tuning")
    write_rows(RAW / "exp09_tuning_results.csv", rows, FIELDS)
    print(f"[tune] wrote {len(rows)} rows in {time.time()-started:.1f}s", flush=True)

    df = pd.DataFrame(rows)
    c0 = df[df["method"] == "C0"].groupby(
        ["topology", "selectivity_pct", "budget"]
    ).agg(c0_recall=("recall_at_10", "mean")).reset_index()
    summary = []
    for (m, eps) in T2_GRID:
        params = f"m={m};eps={eps}"
        t2 = df[df["method"] == "T2"][df["params"] == params]
        merged = t2.groupby(["topology", "selectivity_pct", "budget"]).agg(
            recall=("recall_at_10", "mean"),
            visited=("unique_visited_count", "mean"),
            judgement=("judgement_ns", "mean"),
        ).reset_index().merge(c0, on=["topology", "selectivity_pct", "budget"])
        merged["recall_drop"] = merged["c0_recall"] - merged["recall"]
        merged["visited_reduction"] = 1.0 - merged["visited"] / merged["budget"]
        summary.append({
            "m": m, "epsilon": eps,
            "mean_recall_drop": merged["recall_drop"].mean(),
            "max_group_recall_drop": merged["recall_drop"].max(),
            "mean_visited_reduction": merged["visited_reduction"].mean(),
            "min_group_visited_reduction": merged["visited_reduction"].min(),
            "mean_judgement_ns": merged["judgement"].mean(),
        })
    summary_df = pd.DataFrame(summary)
    write_rows(TABLES / "exp09_tuning_summary.csv", summary_df.to_dict("records"), list(summary_df.columns))

    # Pre-registered selection rule: only candidates meeting all three
    # quantitative gates; among them choose the one with greatest visit
    # reduction, tie-broken by smaller recall drop. Strategy-invariance and
    # overhead gates are checked on the confirmation set (not tuneable).
    eligible = summary_df[
        (summary_df["mean_visited_reduction"] >= 0.20)
        & (summary_df["mean_recall_drop"] <= 0.05)
        & (summary_df["max_group_recall_drop"] <= 0.10)
    ].copy()
    if eligible.empty:
        chosen = None
        print("[tune] NO T2 candidate met all pre-registered quantitative gates", flush=True)
    else:
        eligible = eligible.sort_values(
            ["mean_visited_reduction", "mean_recall_drop"], ascending=[False, True]
        )
        chosen = {"m": int(eligible.iloc[0]["m"]), "epsilon": float(eligible.iloc[0]["epsilon"])}
        print(f"[tune] frozen params: {chosen}", flush=True)
    SELECTED.parent.mkdir(parents=True, exist_ok=True)
    SELECTED.write_text(json.dumps({
        "selected": chosen,
        "rule": "visit_reduction>=0.20 AND mean_recall_drop<=0.05 AND max_group_recall_drop<=0.10",
        "tie_break": "max mean_visited_reduction then min mean_recall_drop",
        "tuning_query_ids": [0, len(tuning_ids) - 1],
    }, indent=2), encoding="utf-8")


def confirm(config) -> None:
    started = time.time()
    if not SELECTED.exists():
        raise SystemExit("no frozen parameter file; run `tune` first")
    frozen = json.loads(SELECTED.read_text(encoding="utf-8"))["selected"]
    dataset, graph, qdist, conditions, top_k, keys = _conditions_and_tools(config)
    nq = dataset.n_queries
    confirm_ids = list(range(nq // 2, nq))
    print(f"[confirm] n_queries={len(confirm_ids)} frozen={frozen}", flush=True)

    # Tuning froze NO parameter (all four T2 configs failed the pre-registered
    # recall gates). Per the pre-registration we do not expand the grid or add
    # mechanisms to rescue it. The four tuning configs are replayed ONCE on the
    # confirmation set purely to document the negative result; no parameter is
    # selected from these rows. C0 and T1 are the policy-oblivious comparators.
    methods = [("C0", "full_budget")]
    methods += [("T1", f) for f in T1_FRACTIONS]
    methods += [("T2", g) for g in T2_GRID]
    rows = run_stop_rows(conditions, qdist, graph, top_k, methods, confirm_ids, "confirmation")

    # E1/E2 references on selected conditions: budget 200 and 500,
    # all topology x selectivity. Derived from the same frozen plan.
    ref_rows = []
    for ctx in conditions:
        if ctx.budget not in (200, 500):
            continue
        for q in confirm_ids:
            plan = ctx.plans[q]
            mask = ctx.policy.mask
            e1_full = adaptive_postfilter_from_plan(
                plan[0], plan[1], plan[2], qdist[q], 500, mask, top_k, 20, q, graph=graph
            )
            for budget in (ctx.budget,):
                e1 = truncate_outcome(e1_full, budget, graph, qdist[q], mask, top_k) \
                    if e1_full.budget != budget else e1_full
                ref_rows.append(_ref_row("E1_POSTFILTER", ctx, q, e1))
            for r in (1, 2):
                e2 = predicate_aware_search(
                    qdist[q], graph, ctx.budget, mask, top_k, r, 20, q
                )
                ref_rows.append(_ref_row(f"E2_BRIDGE_r{r}", ctx, q, e2))
    write_rows(RAW / "exp09_confirmation_results.csv", rows, FIELDS)
    write_rows(RAW / "exp09_reference_results.csv", ref_rows, FIELDS)

    inv_methods = list(methods)
    inv_rows = run_invariance_rows(
        [c for c in conditions if c.topology == "random"],
        qdist, graph, top_k, inv_methods, confirm_ids, "confirmation", keys,
    )
    write_rows(RAW / "exp09_invariance_results.csv", inv_rows, INV_FIELDS)
    print(f"[confirm] wrote {len(rows)} stop rows, {len(ref_rows)} ref rows, "
          f"{len(inv_rows)} invariance rows in {time.time()-started:.1f}s", flush=True)


def _ref_row(algorithm: str, ctx, q: int, outcome) -> dict:
    return {
        "phase": "confirmation", "topology": ctx.topology,
        "selectivity_pct": round(ctx.selectivity * 100, 4),
        "budget": ctx.budget, "method": "REFERENCE", "params": algorithm,
        "query_id": q, "split": "confirmation", "algorithm": algorithm,
        "recall_at_10": recall_at_k(outcome, ctx.gt.indices[q]),
        "gt_size": len(ctx.gt.indices[q]),
        "insufficient_gt": int(ctx.gt.insufficient(q)),
        "unique_visited_count": outcome.unique_visited_count,
        "neighbor_checks_count": outcome.neighbor_checks_count,
        "expanded_nodes_count": outcome.expanded_nodes_count,
        "stop_position": outcome.stop_position, "stop_reason": "reference",
        "wall_ns": 0, "judgement_ns": 0, "delta_checks": 0,
        "trace_sha16": trace_hash(outcome.visited_nodes),
        "seed": ctx.seed, "sigma": ctx.sigma,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"tune", "confirm", "verify"}:
        raise SystemExit("usage: run_exp09.py {tune|confirm|verify}")
    cfg = cli_config([])
    {"tune": tune, "confirm": confirm, "verify": verify_plans}[sys.argv[1]](cfg)
