"""EXP-09.1: Oracle Prefix Feasibility Analysis (offline diagnostic only).

This program answers one question with data already produced by EXP-09:

    For a fixed query, is there a short prefix of the public E3 visit plan that
    simultaneously reaches near-full Recall@10 under two authorization-policy
    distributions (random and clustered), when the prefix length must be the
    SAME for both policies?

The authorization masks are used ONLY after traversal to evaluate recall.
They are never passed to the traversal/stopping logic. This is an idealized
EX-POST oracle: ``t*`` is computed with knowledge of the full-budget recall and
cannot be implemented as an online stopping rule. It is a feasibility bound,
not a new stop algorithm and not a claim of query/output privacy.

Inputs (read-only):
  config/experiment.yaml
  results/raw/exp09_confirmation_results.csv   (C0 / T1 80% / T2 m16 eps0.001)

Outputs:
  results/analysis/exp09_oracle_prefix.csv
  results/analysis/exp09_oracle_summary.csv
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from experiments.exp_common import cli_config, prepare  # noqa: E402
from experiments.exp09_common import (  # noqa: E402
    BUDGETS,
    SELECTIVITIES,
    TOPOLOGIES,
    FullBudgetStopper,
    build_conditions,
    trace_hash,
)
from pa_vfann.metrics import recall_at_k  # noqa: E402
from pa_vfann.policy_oblivious_stop import run_stop_search  # noqa: E402
from pa_vfann.search_common import truncate_outcome  # noqa: E402

CONFIRM_IDS = tuple(range(100, 200))       # EXP-09 confirmation set
DELTAS = (0.05, 0.10)
MIN_PREFIX_FRACTION = 0.6                  # same earliest check as EXP-09 T2
EPS = 1e-12                                # tolerance, avoids float-boundary artifacts
T1_80_PARAMS = "c=0.80"
T2_BEST_PARAMS = "m=16;eps=0.001"          # best mean-recall T2 config in EXP-09
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261125

PREFIX_FIELDS = [
    "phase", "query_id", "policy_type", "selectivity_pct", "budget", "delta",
    "seed", "sigma", "trace_sha16", "min_prefix_t", "gt_size", "insufficient_gt",
    "recall_full_B", "recall_at_t_star", "t_star", "t_star_frac", "prefix_evals",
]

SUMMARY_FIELDS = [
    "scope", "selectivity_pct", "budget", "delta", "n_queries", "n_observations",
    "t_random_B_mean", "t_clustered_B_mean", "paired_diff_B_mean",
    "paired_diff_B_ci_lo", "paired_diff_B_ci_hi",
    "t_robust_B_mean", "t_robust_B_ci_lo", "t_robust_B_ci_hi",
    "t_robust_B_median", "t_robust_B_p90",
    "frac_robust_le_08", "frac_robust_le_08_ci_lo", "frac_robust_le_08_ci_hi",
    "frac_robust_le_09", "frac_robust_le_09_ci_lo", "frac_robust_le_09_ci_hi",
    "frac_oracle_le_t2", "frac_oracle_le_t2_ci_lo", "frac_oracle_le_t2_ci_hi",
    "e3_full_recall_mean", "t1_80_stop_frac", "t1_80_recall_mean", "t1_80_recall_drop",
    "t2_best_stop_frac", "t2_best_recall_mean", "t2_best_recall_drop",
]


def _key(topology: str, selectivity: float, budget: int, query_id: int):
    return (topology, round(float(selectivity) * 100, 4), int(budget), int(query_id))


def load_confirmation() -> pd.DataFrame:
    path = ROOT / "results" / "raw" / "exp09_confirmation_results.csv"
    if not path.exists():
        raise SystemExit(f"missing EXP-09 confirmation data: {path}")
    return pd.read_csv(path)


def compute_prefix_rows(config, confirm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Reconstruct E3 prefixes and compute the ex-post t* for every condition."""
    c0 = confirm[confirm["method"] == "C0"]
    c0_recall = c0.set_index(
        ["topology", "selectivity_pct", "budget", "query_id"]
    )["recall_at_10"].to_dict()
    c0_trace = c0.set_index(
        ["topology", "selectivity_pct", "budget", "query_id"]
    )["trace_sha16"].to_dict()

    dataset, graph, qdist = prepare(config)
    conditions, top_k = build_conditions(config, dataset, graph, qdist)
    rows: list[dict] = []
    checks = {"trace_mismatches": 0, "recall_max_diff": 0.0, "rb_endpoint_mismatches": 0}
    started = time.time()

    for ctx in conditions:
        for q in CONFIRM_IDS:
            row = np.asarray(qdist[q])
            full, _, _ = run_stop_search(
                "E3_FULL_ORACLE", row, graph, ctx.budget, ctx.policy.mask,
                top_k, FullBudgetStopper(), q,
            )
            key = _key(ctx.topology, ctx.selectivity, ctx.budget, q)
            if trace_hash(full.visited_nodes) != c0_trace[key]:
                checks["trace_mismatches"] += 1
            recall_full = recall_at_k(full, ctx.gt.indices[q])
            checks["recall_max_diff"] = max(
                checks["recall_max_diff"], abs(recall_full - float(c0_recall[key]))
            )

            min_t = math.ceil(MIN_PREFIX_FRACTION * ctx.budget)
            curve: list[tuple[int, float]] = []
            for t in range(min_t, ctx.budget + 1):
                prefix = truncate_outcome(full, t, graph, row, ctx.policy.mask, top_k)
                curve.append((t, recall_at_k(prefix, ctx.gt.indices[q])))
            if abs(curve[-1][1] - recall_full) > EPS:
                checks["rb_endpoint_mismatches"] += 1

            for delta in DELTAS:
                threshold = recall_full - float(delta)
                t_star, recall_t_star = next(
                    (t, r) for t, r in curve if r >= threshold - EPS
                )
                rows.append({
                    "phase": "oracle_prefix",
                    "query_id": q,
                    "policy_type": ctx.topology,       # policy distribution, not graph topology
                    "selectivity_pct": round(ctx.selectivity * 100, 4),
                    "budget": int(ctx.budget),
                    "delta": float(delta),
                    "seed": ctx.seed,
                    "sigma": ctx.sigma,
                    "trace_sha16": trace_hash(full.visited_nodes),
                    "min_prefix_t": min_t,
                    "gt_size": len(ctx.gt.indices[q]),
                    "insufficient_gt": int(ctx.gt.insufficient(q)),
                    "recall_full_B": recall_full,
                    "recall_at_t_star": recall_t_star,
                    "t_star": t_star,
                    "t_star_frac": t_star / ctx.budget,
                    "prefix_evals": len(curve),
                })

    print(f"[oracle] {len(rows)} prefix rows in {time.time() - started:.1f}s; "
          f"checks={checks}", flush=True)
    if checks["trace_mismatches"] or checks["rb_endpoint_mismatches"] or checks["recall_max_diff"] > EPS:
        raise SystemExit(f"[oracle] EXP-09 cross-check failed: {checks}")
    return pd.DataFrame(rows, columns=PREFIX_FIELDS), checks


def robust_prefixes(prefix: pd.DataFrame) -> pd.DataFrame:
    """Pair random/clustered policies on the same query/selectivity/budget/delta."""
    keys = ["query_id", "selectivity_pct", "budget", "delta"]
    a = prefix[prefix["policy_type"] == "random"].rename(columns={
        "t_star": "t_star_random", "t_star_frac": "t_random_B_frac",
        "recall_full_B": "recall_full_random",
    })
    b = prefix[prefix["policy_type"] == "clustered"].rename(columns={
        "t_star": "t_star_clustered", "t_star_frac": "t_clustered_B_frac",
        "recall_full_B": "recall_full_clustered",
    })
    a_cols = keys + ["t_star_random", "t_random_B_frac", "recall_full_random"]
    b_cols = keys + ["t_star_clustered", "t_clustered_B_frac", "recall_full_clustered"]
    rob = a[a_cols].merge(b[b_cols], on=keys, validate="one_to_one")
    rob["t_robust"] = rob[["t_star_random", "t_star_clustered"]].max(axis=1)
    rob["t_robust_B_frac"] = rob["t_robust"] / rob["budget"]
    rob["paired_diff_B_frac"] = rob["t_random_B_frac"] - rob["t_clustered_B_frac"]
    rob["le_08"] = (rob["t_robust_B_frac"] <= 0.8 + EPS).astype(int)
    rob["le_09"] = (rob["t_robust_B_frac"] <= 0.9 + EPS).astype(int)
    return rob.sort_values(keys).reset_index(drop=True)


def bootstrap_ci(matrix: np.ndarray, seed_offset: int) -> tuple[float, float]:
    """Query-level paired bootstrap CI for a row-level mean/proportion.

    ``matrix`` has shape (n_queries, n_observations_per_query). Resampling is
    done over query IDs, keeping all of that query's observations together.
    """
    nq = matrix.shape[0]
    rng = np.random.default_rng(BOOTSTRAP_SEED + seed_offset)
    idx = rng.integers(0, nq, size=(N_BOOTSTRAP, nq))
    estimates = matrix[idx].mean(axis=(1, 2))
    return tuple(float(v) for v in np.percentile(estimates, [2.5, 97.5]))


def _matrix(df: pd.DataFrame, col: str) -> np.ndarray:
    sizes = df.groupby("query_id").size()
    if sizes.nunique() != 1:
        raise SystemExit(f"unequal observation counts per query for {col}")
    qids = sorted(sizes.index.tolist())
    return df.sort_values(["query_id", "selectivity_pct", "budget"])[col].to_numpy().reshape(
        len(qids), int(sizes.iloc[0])
    )


def baseline_lookup(confirm: pd.DataFrame):
    """Per-group values for C0 / T1 80% / T2 best-recall config."""
    c0 = confirm[confirm["method"] == "C0"].groupby(
        ["topology", "selectivity_pct", "budget"]
    )["recall_at_10"].mean().to_dict()
    out = {}
    for label, method, params in (
        ("t1_80", "T1", T1_80_PARAMS),
        ("t2_best", "T2", T2_BEST_PARAMS),
    ):
        sub = confirm[(confirm["method"] == method) & (confirm["params"] == params)]
        if sub.empty:
            raise SystemExit(f"missing EXP-09 baseline {method} {params}")
        g = sub.groupby(["topology", "selectivity_pct", "budget"]).agg(
            recall=("recall_at_10", "mean"), stop=("stop_position", "mean")
        )
        for (topo, sel, bud), r in g.iterrows():
            out[(label, topo, float(sel), int(bud))] = (
                float(r["stop"]) / int(bud),
                float(r["recall"]),
                float(c0[(topo, sel, bud)]) - float(r["recall"]),
            )
    return c0, out


def summarize(rob: pd.DataFrame, confirm: pd.DataFrame) -> pd.DataFrame:
    c0_map, base = baseline_lookup(confirm)
    t2_obs = confirm[
        (confirm["method"] == "T2") & (confirm["params"] == T2_BEST_PARAMS)
        & (confirm["topology"] == "random")
    ].set_index(["selectivity_pct", "budget", "query_id"])["stop_position"]
    rows: list[dict] = []

    def group_specs():
        for delta in DELTAS:
            yield ("ALL", None, None, delta, rob[rob["delta"] == delta])
            for sel in SELECTIVITIES:
                for bud in BUDGETS:
                    sub = rob[(rob["delta"] == delta)
                              & (np.isclose(rob["selectivity_pct"], sel * 100))
                              & (rob["budget"] == bud)]
                    yield ("group", sel * 100, bud, delta, sub)

    for n, (scope, sel, bud, delta, sub) in enumerate(group_specs()):
        if sub.empty:
            raise SystemExit(f"empty oracle group: {scope} {sel} {bud} {delta}")
        idx = pd.MultiIndex.from_frame(sub[["selectivity_pct", "budget", "query_id"]])
        stops = t2_obs.reindex(idx).to_numpy()
        if np.isnan(stops).any():
            raise SystemExit(f"missing T2 realized stop position for group {scope} {sel} {bud}")
        sub = sub.assign(oracle_le_t2=(sub["t_robust"].to_numpy() <= stops + EPS).astype(int))
        nq = sub["query_id"].nunique()
        if nq != len(CONFIRM_IDS):
            raise SystemExit(f"expected 100 confirmation queries, got {nq}")

        m = {
            "t_random_B_frac": _matrix(sub, "t_random_B_frac"),
            "t_clustered_B_frac": _matrix(sub, "t_clustered_B_frac"),
            "paired_diff_B_frac": _matrix(sub, "paired_diff_B_frac"),
            "t_robust_B_frac": _matrix(sub, "t_robust_B_frac"),
            "le_08": _matrix(sub, "le_08"),
            "le_09": _matrix(sub, "le_09"),
            "oracle_le_t2": _matrix(sub, "oracle_le_t2"),
        }
        ci_rob = bootstrap_ci(m["t_robust_B_frac"], n * 7 + 0)
        ci_diff = bootstrap_ci(m["paired_diff_B_frac"], n * 7 + 1)
        ci_08 = bootstrap_ci(m["le_08"], n * 7 + 2)
        ci_09 = bootstrap_ci(m["le_09"], n * 7 + 3)
        ci_t2 = bootstrap_ci(m["oracle_le_t2"], n * 7 + 4)

        if scope == "ALL":
            c0_mean = float(np.mean(list(c0_map.values())))
            b1 = [v for k, v in base.items() if k[0] == "t1_80"]
            b2 = [v for k, v in base.items() if k[0] == "t2_best"]
        else:
            keys = [(topo, float(sel), int(bud)) for topo in TOPOLOGIES]
            c0_mean = float(np.mean([c0_map[k] for k in keys]))
            b1 = [base[("t1_80", *k)] for k in keys]
            b2 = [base[("t2_best", *k)] for k in keys]

        rows.append({
            "scope": scope,
            "selectivity_pct": "" if sel is None else round(float(sel), 4),
            "budget": "" if bud is None else int(bud),
            "delta": float(delta),
            "n_queries": nq,
            "n_observations": len(sub),
            "t_random_B_mean": round(float(m["t_random_B_frac"].mean()), 4),
            "t_clustered_B_mean": round(float(m["t_clustered_B_frac"].mean()), 4),
            "paired_diff_B_mean": round(float(m["paired_diff_B_frac"].mean()), 4),
            "paired_diff_B_ci_lo": round(ci_diff[0], 4),
            "paired_diff_B_ci_hi": round(ci_diff[1], 4),
            "t_robust_B_mean": round(float(m["t_robust_B_frac"].mean()), 4),
            "t_robust_B_ci_lo": round(ci_rob[0], 4),
            "t_robust_B_ci_hi": round(ci_rob[1], 4),
            "t_robust_B_median": round(float(np.median(sub["t_robust_B_frac"])), 4),
            "t_robust_B_p90": round(float(np.percentile(sub["t_robust_B_frac"], 90)), 4),
            "frac_robust_le_08": round(float(m["le_08"].mean()), 4),
            "frac_robust_le_08_ci_lo": round(ci_08[0], 4),
            "frac_robust_le_08_ci_hi": round(ci_08[1], 4),
            "frac_robust_le_09": round(float(m["le_09"].mean()), 4),
            "frac_robust_le_09_ci_lo": round(ci_09[0], 4),
            "frac_robust_le_09_ci_hi": round(ci_09[1], 4),
            "frac_oracle_le_t2": round(float(m["oracle_le_t2"].mean()), 4),
            "frac_oracle_le_t2_ci_lo": round(ci_t2[0], 4),
            "frac_oracle_le_t2_ci_hi": round(ci_t2[1], 4),
            "e3_full_recall_mean": round(c0_mean, 4),
            "t1_80_stop_frac": round(float(np.mean([v[0] for v in b1])), 4),
            "t1_80_recall_mean": round(float(np.mean([v[1] for v in b1])), 4),
            "t1_80_recall_drop": round(float(np.mean([v[2] for v in b1])), 4),
            "t2_best_stop_frac": round(float(np.mean([v[0] for v in b2])), 4),
            "t2_best_recall_mean": round(float(np.mean([v[1] for v in b2])), 4),
            "t2_best_recall_drop": round(float(np.mean([v[2] for v in b2])), 4),
        })
    return pd.DataFrame(rows, columns=SUMMARY_FIELDS)


def main() -> None:
    config = cli_config([])
    confirm = load_confirmation()
    prefix, checks = compute_prefix_rows(config, confirm)
    rob = robust_prefixes(prefix)
    summary = summarize(rob, confirm)

    out = ROOT / "results" / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    prefix.to_csv(out / "exp09_oracle_prefix.csv", index=False)
    rob.to_csv(out / "exp09_oracle_robust.csv", index=False)   # paired detail, audit trail
    summary.to_csv(out / "exp09_oracle_summary.csv", index=False)

    print("[oracle] consistency:", json_compatible(checks), flush=True)
    for _, r in summary[summary["scope"] == "ALL"].iterrows():
        print(f"[oracle] delta={r['delta']:.2f} robust/B mean={r['t_robust_B_mean']:.4f} "
              f"median={r['t_robust_B_median']:.4f} p90={r['t_robust_B_p90']:.4f} "
              f"P(<=0.8B)={r['frac_robust_le_08']:.4f} P(<=0.9B)={r['frac_robust_le_09']:.4f}",
              flush=True)


def json_compatible(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())


if __name__ == "__main__":
    main()
