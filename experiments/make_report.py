"""Build summary tables and the four required figures from raw CSVs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pa_vfann.config import default_config_path, load_config  # noqa: E402

ALG_ORDER = ["E1_POSTFILTER", "E2_BRIDGE_r1", "E2_BRIDGE_r2", "E2_BRIDGE_r4", "E3_FIXED_TRACE"]
ALG_LABEL = {
    "E1_POSTFILTER": "E1 post-filter",
    "E2_BRIDGE_r1": "E2 bridge r=1",
    "E2_BRIDGE_r2": "E2 bridge r=2",
    "E2_BRIDGE_r4": "E2 bridge r=4",
    "E3_FIXED_TRACE": "E3 fixed-trace",
}
STYLES = {
    "E1_POSTFILTER": ("-", "o"),
    "E2_BRIDGE_r1": ("--", "s"),
    "E2_BRIDGE_r2": ("-.", "^"),
    "E2_BRIDGE_r4": (":", "D"),
    "E3_FIXED_TRACE": ("-", "v"),
}


def canonical_algorithm(row: pd.Series) -> str:
    if row["algorithm"] == "E2_BRIDGE":
        return f"E2_BRIDGE_r{int(row['bridge_r'])}"
    return row["algorithm"]


def build_tables(raw: pd.DataFrame, tables_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = raw[raw["experiment"] == "selectivity"].copy()
    df["algorithm_key"] = df.apply(canonical_algorithm, axis=1)
    grouped = df.groupby(
        ["policy_type", "selectivity_pct", "algorithm_key", "budget"], as_index=False
    ).agg(
        trials=("recall_at_10", "size"),
        recall_mean=("recall_at_10", "mean"),
        recall_std=("recall_at_10", "std"),
        recall_p95=("recall_at_10", lambda x: np.percentile(x, 95)),
        unique_visited_mean=("unique_visited_count", "mean"),
        unique_visited_p95=("unique_visited_count", lambda x: np.percentile(x, 95)),
        expanded_nodes_mean=("expanded_nodes_count", "mean"),
        neighbor_checks_mean=("neighbor_checks_count", "mean"),
        legal_candidates_mean=("legal_candidates_count", "mean"),
        returned_count_mean=("returned_count", "mean"),
        insufficient_rate=("insufficient_gt", "mean"),
    )
    grouped.to_csv(tables_dir / "summary_by_selectivity.csv", index=False)

    target = float(load_config(default_config_path())["search"]["target_recall"])
    rows = []
    for keys, group in grouped.groupby(["policy_type", "selectivity_pct", "algorithm_key"]):
        reached = group[group["recall_mean"] >= target]
        rows.append({
            "policy_type": keys[0],
            "selectivity_pct": keys[1],
            "algorithm": keys[2],
            "min_budget_reaching_090": int(reached["budget"].min()) if len(reached) else "NOT_REACHED",
            "max_mean_recall": float(group["recall_mean"].max()),
            "n_budgets_evaluated": int(group["budget"].nunique()),
        })
    budget_table = pd.DataFrame(rows).sort_values(
        ["policy_type", "selectivity_pct", "algorithm"]
    )
    budget_table.to_csv(tables_dir / "budget_to_recall_090.csv", index=False)
    return grouped, budget_table


def plot_recall_vs_budget(grouped: pd.DataFrame, figures_dir: Path) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(18, 8), sharex=True, sharey=True)
    for i, policy in enumerate(["random", "clustered"]):
        for j, sel in enumerate(sorted(grouped["selectivity_pct"].unique())):
            ax = axes[i, j]
            subset = grouped[(grouped["policy_type"] == policy) & (grouped["selectivity_pct"] == sel)]
            for alg in ALG_ORDER:
                part = subset[subset["algorithm_key"] == alg].sort_values("budget")
                if part.empty:
                    continue
                line, marker = STYLES[alg]
                ax.plot(part["budget"], part["recall_mean"], line, marker=marker,
                        ms=4, label=ALG_LABEL[alg], linewidth=1.5)
            ax.axhline(0.9, color="grey", lw=0.8, ls=":")
            ax.set_title(f"{policy} / {sel:g}%")
            ax.set_xscale("log", base=2)
            ax.grid(alpha=0.25)
            if j == 0:
                ax.set_ylabel("Recall@10")
            if i == 1:
                ax.set_xlabel("budget (unique visited nodes)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Recall@10 vs search budget (mean over 200 queries)")
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(figures_dir / "recall_vs_budget.png", dpi=170)
    plt.close(fig)


def plot_budget_to_recall(table: pd.DataFrame, figures_dir: Path, max_budget: int) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, policy in zip(axes, ["random", "clustered"]):
        subset = table[table["policy_type"] == policy]
        sels = sorted(subset["selectivity_pct"].unique())
        x = np.arange(len(sels))
        width = 0.16
        for k, alg in enumerate(ALG_ORDER):
            values = []
            labels = []
            for sel in sels:
                row = subset[(subset["selectivity_pct"] == sel) & (subset["algorithm"] == alg)]
                value = row["min_budget_reaching_090"].iloc[0] if len(row) else "NOT_REACHED"
                values.append(max_budget if value == "NOT_REACHED" else int(value))
                labels.append("NR" if value == "NOT_REACHED" else str(value))
            bars = ax.bar(x + (k - 2) * width, values, width, label=ALG_LABEL[alg])
            for bar, label in zip(bars, labels):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 12,
                        label, ha="center", va="bottom", fontsize=7, rotation=45)
        ax.set_ylim(0, max_budget * 1.18)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{sel:g}%" for sel in sels])
        ax.set_title(policy)
        ax.set_ylabel("min budget for mean Recall@10 >= 0.90")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Cost to reach the 0.90 recall target (NR = not reached at any budget)")
    fig.tight_layout()
    fig.savefig(figures_dir / "budget_to_recall.png", dpi=170)
    plt.close(fig)


def plot_p95(grouped: pd.DataFrame, figures_dir: Path) -> None:
    subset = grouped[grouped["budget"] == 500]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, policy in zip(axes, ["random", "clustered"]):
        part = subset[subset["policy_type"] == policy]
        sels = sorted(part["selectivity_pct"].unique())
        x = np.arange(len(sels))
        width = 0.16
        for k, alg in enumerate(ALG_ORDER):
            values = [
                part[(part["selectivity_pct"] == sel) & (part["algorithm_key"] == alg)]["unique_visited_p95"].iloc[0]
                if len(part[(part["selectivity_pct"] == sel) & (part["algorithm_key"] == alg)]) else 0
                for sel in sels
            ]
            ax.bar(x + (k - 2) * width, values, width, label=ALG_LABEL[alg])
        ax.set_xticks(x)
        ax.set_xticklabels([f"{sel:g}%" for sel in sels])
        ax.set_ylabel("P95 unique visited nodes")
        ax.set_title(policy)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("P95 access cost at budget=500")
    fig.tight_layout()
    fig.savefig(figures_dir / "p95_access_nodes.png", dpi=170)
    plt.close(fig)


def plot_leakage(figures_dir: Path) -> None:
    path = figures_dir.parent / "tables" / "leakage_summary.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    df = df[df["budget"] == 500]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    for ax, metric in zip(axes, ["L_set_mean", "L_seq_mean"]):
        pairs = df["policy_pair"].unique().tolist()
        x = np.arange(len(pairs))
        width = 0.25
        for k, alg in enumerate(["E1_POSTFILTER", "E2_BRIDGE", "E3_FIXED_TRACE"]):
            values = [
                df[(df["policy_pair"] == pair) & (df["algorithm"] == alg)][metric].iloc[0]
                if len(df[(df["policy_pair"] == pair) & (df["algorithm"] == alg)]) else 0
                for pair in pairs
            ]
            bars = ax.bar(x + (k - 1) * width, values, width, label=alg)
            for bar, value in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, value + 0.008,
                        f"{value:.3f}", ha="center", va="bottom", fontsize=7, rotation=45)
        ax.set_ylim(0, 0.95)
        ax.set_xticks(x)
        ax.set_xticklabels(pairs, rotation=18, ha="right", fontsize=8)
        ax.set_ylabel(metric)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Trace leakage across authorization policies (budget=500)")
    fig.tight_layout()
    fig.savefig(figures_dir / "trace_leakage.png", dpi=170)
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw_path = root / "results" / "raw" / "experiment_results.csv"
    tables_dir = root / "results" / "tables"
    figures_dir = root / "results" / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(raw_path)
    grouped, budget_table = build_tables(raw, tables_dir)
    max_budget = int(raw["budget"].max())
    plot_recall_vs_budget(grouped, figures_dir)
    plot_budget_to_recall(budget_table, figures_dir, max_budget)
    plot_p95(grouped, figures_dir)
    plot_leakage(figures_dir)
    print(f"[report] tables in {tables_dir}, figures in {figures_dir}")


if __name__ == "__main__":
    main()
