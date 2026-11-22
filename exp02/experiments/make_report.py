"""EXP-02 summary tables and five core figures from the raw CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pa_vfann_exp02.config import load_config  # noqa: E402

ALG_ORDER = ["E1_POSTFILTER", "E2_BRIDGE_r1", "E2_BRIDGE_r2", "E2_BRIDGE_r4", "E3_FIXED_TRACE"]
ALG_LABEL = {
    "E1_POSTFILTER": "E1 post-filter",
    "E2_BRIDGE_r1": "E2 bridge r=1",
    "E2_BRIDGE_r2": "E2 bridge r=2",
    "E2_BRIDGE_r4": "E2 bridge r=4",
    "E3_FIXED_TRACE": "E3 fixed-trace",
}
STYLES = {
    "E1_POSTFILTER": ("-", "o"), "E2_BRIDGE_r1": ("--", "s"),
    "E2_BRIDGE_r2": ("-.", "^"), "E2_BRIDGE_r4": (":", "D"),
    "E3_FIXED_TRACE": ("-", "v"),
}
COST_COLUMNS = [
    "distance_evaluations", "unique_discovered_nodes", "unique_visited_nodes",
    "expanded_nodes", "neighbor_checks", "candidate_count", "candidate_transfer_bytes",
]


def canon(row: pd.Series) -> str:
    if row["algorithm"] == "E2_BRIDGE":
        return f"E2_BRIDGE_r{int(float(row['bridge_r']))}"
    return row["algorithm"]


def build_tables(raw: pd.DataFrame, tables: Path, target: float, ref_budget: int):
    sel = raw[raw["experiment"] == "selectivity"].copy()
    sel["algorithm_key"] = sel.apply(canon, axis=1)
    grouped = sel.groupby(
        ["policy_type", "selectivity_pct", "algorithm_key", "budget"], as_index=False
    ).agg(
        trials=("recall_at_10", "size"),
        recall_mean=("recall_at_10", "mean"),
        recall_std=("recall_at_10", "std"),
        recall_p95=("recall_at_10", lambda x: np.percentile(x.dropna(), 95) if x.notna().any() else np.nan),
        failed_queries=("recall_at_10", lambda x: int((x < target).sum())),
        na_recall_count=("recall_at_10", lambda x: int(x.isna().sum())),
        distance_evaluations_mean=("distance_evaluations", "mean"),
        distance_evaluations_p95=("distance_evaluations", lambda x: np.percentile(x, 95)),
        unique_discovered_mean=("unique_discovered_nodes", "mean"),
        unique_visited_mean=("unique_visited_nodes", "mean"),
        unique_visited_p95=("unique_visited_nodes", lambda x: np.percentile(x, 95)),
        expanded_nodes_mean=("expanded_nodes", "mean"),
        expanded_nodes_p95=("expanded_nodes", lambda x: np.percentile(x, 95)),
        neighbor_checks_mean=("neighbor_checks", "mean"),
        candidate_count_mean=("candidate_count", "mean"),
        candidate_count_p95=("candidate_count", lambda x: np.percentile(x, 95)),
        candidate_transfer_bytes_mean=("candidate_transfer_bytes", "mean"),
        candidate_transfer_bytes_p95=("candidate_transfer_bytes", lambda x: np.percentile(x, 95)),
        returned_count_mean=("returned_count", "mean"),
        early_stop_rate=("termination_reason", lambda x: float((x == "early_stop").mean())),
    )
    grouped.to_csv(tables / "summary_by_selectivity.csv", index=False)

    rows = []
    keys = ["policy_type", "selectivity_pct", "algorithm_key"]
    for key, group in grouped.groupby(keys):
        reached = group[group["recall_mean"] >= target]
        budget_hit = int(reached["budget"].min()) if len(reached) else "NOT_REACHED"
        by_query = sel[
            (sel["policy_type"] == key[0])
            & (sel["selectivity_pct"] == key[1])
            & (sel["algorithm_key"] == key[2])
            & (sel["recall_at_10"] >= target)
        ]
        rows.append({
            "policy_type": key[0], "selectivity_pct": key[1], "algorithm": key[2],
            "min_budget_reaching_090": budget_hit,
            "max_mean_recall": float(group["recall_mean"].max()),
            "distance_evaluations_at_target": int(reached["distance_evaluations_mean"].min()) if len(reached) else "NOT_REACHED",
            "transfer_bytes_at_target": int(reached["candidate_transfer_bytes_mean"].min()) if len(reached) else "NOT_REACHED",
            "min_distance_evaluations_any_query_at_target": int(by_query["distance_evaluations"].min()) if len(by_query) else "NOT_REACHED",
            "min_transfer_bytes_any_query_at_target": int(by_query["candidate_transfer_bytes"].min()) if len(by_query) else "NOT_REACHED",
        })
    budget_table = pd.DataFrame(rows).sort_values(["policy_type", "selectivity_pct", "algorithm"])
    budget_table.to_csv(tables / "budget_to_recall_090.csv", index=False)

    at_ref = grouped[grouped["budget"] == ref_budget].copy()
    if at_ref.empty:
        at_ref = grouped[grouped["budget"] == grouped["budget"].max()].copy()
    cost_cols = ["distance_evaluations_mean", "distance_evaluations_p95",
                 "unique_discovered_mean", "unique_visited_mean", "expanded_nodes_mean",
                 "neighbor_checks_mean", "candidate_count_mean", "candidate_count_p95",
                 "candidate_transfer_bytes_mean", "candidate_transfer_bytes_p95"]
    cost = at_ref[["policy_type", "selectivity_pct", "algorithm_key"] + cost_cols].copy()
    e1 = cost[cost["algorithm_key"] == "E1_POSTFILTER"].set_index(["policy_type", "selectivity_pct"])
    for metric in ("distance_evaluations_mean", "candidate_transfer_bytes_mean"):
        vals = []
        for _, row in cost.iterrows():
            key = (row["policy_type"], row["selectivity_pct"])
            base = e1.loc[key, metric] if key in e1.index else np.nan
            vals.append(float(row[metric]) / float(base) if base and base > 0 else np.nan)
        cost[f"{metric}_ratio_vs_E1"] = vals
    cost = cost.rename(columns={"algorithm_key": "algorithm"})
    cost.to_csv(tables / "cost_breakdown.csv", index=False)

    leak = raw[raw["experiment"] == "leakage"].copy()
    if not leak.empty:
        leak["algorithm_key"] = leak.apply(canon, axis=1)
        lg = leak.groupby(["pair_name", "algorithm_key", "budget"], as_index=False).agg(
            trials=("query_id", "size"),
            discovery_leakage_mean=("discovery_leakage", "mean"),
            visit_leakage_mean=("visit_leakage", "mean"),
            expansion_leakage_mean=("expansion_leakage", "mean"),
            visit_edit_leakage_mean=("visit_edit_leakage", "mean"),
            stop_position_delta_mean=("stop_position_delta", "mean"),
            candidate_count_delta_mean=("candidate_count_delta", "mean"),
            returned_count_delta_mean=("returned_count_delta", "mean"),
            output_id_leakage_mean=("output_id_leakage", "mean"),
            identical_discovery_rate=("identical_discovery", "mean"),
            identical_visit_rate=("identical_visit", "mean"),
            identical_expansion_rate=("identical_expansion", "mean"),
        )
        lg = lg.rename(columns={"algorithm_key": "algorithm"})
        lg.to_csv(tables / "leakage_summary.csv", index=False)
    else:
        lg = pd.DataFrame()

    max_budget = int(sel["budget"].max())
    failed = sel[(sel["budget"] == max_budget) & (sel["recall_at_10"] < target)]
    failed_cols = ["policy_type", "selectivity_pct", "algorithm_key", "query_id",
                   "recall_at_10", "gt_size", "distance_evaluations", "candidate_transfer_bytes",
                   "termination_reason"]
    failed[failed_cols].rename(columns={"algorithm_key": "algorithm"}).to_csv(
        tables / "failed_queries.csv", index=False,
    )
    return grouped, budget_table, cost, lg, failed


def plot_lines(grouped, figures: Path, x: str, y: str, name: str, title: str, ylabel: str) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(18, 8), sharex=False, sharey=True)
    policies = sorted(grouped["policy_type"].unique())
    sels = sorted(grouped["selectivity_pct"].unique())
    for i, policy in enumerate(policies):
        for j, sel in enumerate(sels):
            ax = axes[i, j]
            part = grouped[(grouped["policy_type"] == policy) & (grouped["selectivity_pct"] == sel)]
            for alg in ALG_ORDER:
                chunk = part[part["algorithm_key"] == alg].sort_values("budget")
                if chunk.empty:
                    continue
                line, marker = STYLES[alg]
                ax.plot(chunk[x], chunk[y], line, marker=marker, ms=4,
                        linewidth=1.4, label=ALG_LABEL[alg])
            if x == "budget":
                ax.set_xscale("log", base=2)
                ax.axhline(0.9, color="grey", lw=0.8, ls=":")
            ax.set_title(f"{policy} / {sel:g}%", fontsize=9)
            ax.grid(alpha=0.25)
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=9)
            if i == 1:
                ax.set_xlabel("expansion budget" if x == "budget" else "mean Recall@10", fontsize=9)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02), fontsize=9)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(figures / name, dpi=170)
    plt.close(fig)


def plot_p95(grouped: pd.DataFrame, figures: Path, ref_budget: int) -> None:
    subset = grouped[grouped["budget"] == ref_budget]
    if subset.empty:
        subset = grouped[grouped["budget"] == grouped["budget"].max()]
    metrics = [("distance_evaluations_p95", "P95 distance evaluations"),
               ("candidate_transfer_bytes_p95", "P95 candidate transfer bytes")]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
    policies = sorted(subset["policy_type"].unique())
    sels = sorted(subset["selectivity_pct"].unique())
    x = np.arange(len(sels))
    width = 0.16
    for i, (metric, ylabel) in enumerate(metrics):
        for j, policy in enumerate(policies):
            ax = axes[i, j]
            for k, alg in enumerate(ALG_ORDER):
                values = []
                for sel in sels:
                    row = subset[(subset["policy_type"] == policy)
                                 & (subset["selectivity_pct"] == sel)
                                 & (subset["algorithm_key"] == alg)]
                    values.append(float(row[metric].iloc[0]) if len(row) else 0.0)
                ax.bar(x + (k - 2) * width, values, width, label=ALG_LABEL[alg])
            ax.set_xticks(x)
            ax.set_xticklabels([f"{sel:g}%" for sel in sels])
            ax.set_ylabel(ylabel, fontsize=9)
            ax.set_title(policy, fontsize=10)
            ax.grid(axis="y", alpha=0.25)
            ax.legend(fontsize=7)
    fig.suptitle(f"P95 cost breakdown at budget={ref_budget}")
    fig.tight_layout()
    fig.savefig(figures / "p95_cost.png", dpi=170)
    plt.close(fig)


def plot_leakage(lg: pd.DataFrame, figures: Path) -> None:
    if lg.empty:
        return
    budget = int(lg["budget"].max())
    subset = lg[lg["budget"] == budget]
    pairs = list(subset["pair_name"].unique())
    metrics = [("discovery_leakage_mean", "Discovery set leakage"),
               ("visit_leakage_mean", "Visit set leakage")]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    x = np.arange(len(pairs))
    width = 0.25
    algs = ["E1_POSTFILTER", "E2_BRIDGE_r2", "E3_FIXED_TRACE"]
    for ax, (metric, ylabel) in zip(axes, metrics):
        for k, alg in enumerate(algs):
            values = []
            for pair in pairs:
                part = subset[(subset["pair_name"] == pair) & (subset["algorithm"] == alg)]
                values.append(float(part[metric].iloc[0]) if len(part) else 0.0)
            bars = ax.bar(x + (k - 1) * width, values, width, label=ALG_LABEL[alg])
            for bar, value in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.008,
                        f"{value:.3f}", ha="center", va="bottom", fontsize=7, rotation=45)
        ax.set_xticks(x)
        ax.set_xticklabels(pairs, rotation=15, ha="right", fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(f"Policy-pair trace leakage (budget={budget})")
    fig.tight_layout()
    fig.savefig(figures / "trace_leakage.png", dpi=170)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config" / "experiment.yaml"))
    parser.add_argument("--raw", default=str(ROOT / "results" / "raw" / "experiment_results.csv"))
    parser.add_argument("--out", default=str(ROOT / "results"))
    args = parser.parse_args()
    config = load_config(args.config)
    out = Path(args.out)
    tables, figures = out / "tables", out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(args.raw)
    budgets = [int(b) for b in config["search"]["budgets"]]
    ref = 500 if 500 in budgets else max(budgets)
    grouped, budget_table, cost, leak, _ = build_tables(
        raw, tables, float(config["search"]["target_recall"]), ref
    )
    plot_lines(grouped, figures, "budget", "recall_mean", "recall_vs_budget.png",
               "Recall@10 vs expansion budget (no distance oracle)", "mean Recall@10")
    plot_lines(grouped, figures, "recall_mean", "distance_evaluations_mean",
               "distance_evaluations_vs_recall.png",
               "Distance evaluations vs Recall@10", "mean distance evaluations")
    plot_lines(grouped, figures, "recall_mean", "candidate_transfer_bytes_mean",
               "transfer_bytes_vs_recall.png",
               "Candidate transfer bytes vs Recall@10", "mean transfer bytes (ID + metadata)")
    plot_p95(grouped, figures, ref)
    plot_leakage(leak, figures)
    print(f"[report] tables: {tables}, figures: {figures}")


if __name__ == "__main__":
    main()
