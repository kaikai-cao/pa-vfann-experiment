"""Two required figures for EXP-02A (English labels, no font dependency)."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

EXP02A = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP02A / "src"))

from pa_vfann_exp02a.config import load_config  # noqa: E402
from pa_vfann_exp02a.observers import FIELDS, OBSERVERS  # noqa: E402
from pa_vfann_exp02a.transfer_models import MODELS  # noqa: E402

FIG = EXP02A / "results" / "figures"
TABLE = EXP02A / "results" / "tables"
COLORS = {"A": "#888888", "B": "#0b6e75", "C": "#c1661a"}


def transfer_figure(cfg) -> None:
    df = pd.read_csv(TABLE / "transfer_cost_by_attribute_size.csv")
    ref_budget = int(cfg["analysis"]["reference_budget"])
    selections = [("random", 1.0), ("random", 10.0),
                  ("clustered", 1.0), ("clustered", 10.0)]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
    for ax, (policy, sel) in zip(axes.ravel(), selections):
        sub = df[(df.policy_type == policy)
                 & (np.isclose(df.selectivity_pct, sel))
                 & (df.budget == ref_budget)]
        for model in MODELS:
            m = sub[sub.model == model].sort_values("attribute_record_bytes")
            ax.plot(m.attribute_record_bytes, m.mean_bytes, marker="o",
                    ms=3.5, lw=2, color=COLORS[model], label=f"Model {model}")
            if model in ("B", "C"):
                ax.plot(m.attribute_record_bytes, m.p95_bytes, lw=1.1, ls="--",
                        alpha=0.65, color=COLORS[model])
        ax.set_title(f"{policy} policy, selectivity {sel:g}%, budget {ref_budget}")
        ax.set_ylabel("bytes per query (candidate batch)")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="upper left")
    for ax in axes[-1]:
        ax.set_xlabel("authorization attribute record size (bytes, scan parameter)")
    fig.suptitle("E3 communication cost under models A / B / C "
                 "(solid = mean, dashed = P95)", fontsize=13)
    fig.tight_layout()
    out = FIG / "transfer_cost_vs_attribute_size.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"[figure] {out.name}")


def observer_figure() -> None:
    vis = pd.read_csv(TABLE / "observer_visibility_matrix.csv")
    scenarios = [
        ("E3_no_feedback_B", "E3, local filter, no feedback (TLS)"),
        ("E3_feedback_B", "E3, client feedback of Top-K (TLS)"),
        ("E1_B", "E1 server-side filtering (TLS)"),
        ("E3_no_feedback_B_noTLS", "E3, local filter, cleartext payload"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(16, 8.5))
    for ax, (name, title) in zip(axes.ravel(), scenarios):
        sub = vis[vis.scenario == name]
        grid = np.zeros((len(OBSERVERS), len(FIELDS)), dtype=int)
        for i, obs in enumerate(OBSERVERS):
            s = sub[sub.observer == obs].set_index("field")
            for j, field in enumerate(FIELDS):
                grid[i, j] = int(s.loc[field, "visible"])
        ax.imshow(grid, cmap=plt.cm.Greens, vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(FIELDS)))
        ax.set_xticklabels([f.replace("_", "\n") for f in FIELDS], fontsize=7)
        ax.set_yticks(range(len(OBSERVERS)))
        ax.set_yticklabels(OBSERVERS, fontsize=9)
        for i in range(len(OBSERVERS)):
            for j in range(len(FIELDS)):
                ax.text(j, i, "1" if grid[i, j] else "0", ha="center", va="center",
                        fontsize=8, color="white" if grid[i, j] else "#555555")
        ax.set_title(title, fontsize=10)
        ax.grid(False)
    fig.suptitle("Observer visibility matrix (dark = visible)", fontsize=13)
    fig.tight_layout()
    out = FIG / "observer_visibility_comparison.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"[figure] {out.name}")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    transfer_figure(cfg)
    observer_figure()


if __name__ == "__main__":
    main()
