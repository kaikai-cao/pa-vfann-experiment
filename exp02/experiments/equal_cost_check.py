"""Supplementary diagnostic: E3 recall at very small expansion budgets.

The frozen grid starts at 20 expansions, which already discovers ~2,100 nodes
on this graph. This diagnostic adds 1/2/5/10 expansions so the recall can be
read as a function of *actual distance evaluations* rather than of the EXP-01
"visited nodes" budget. It does not change the frozen experiment grid.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pa_vfann_exp02.algorithms import run_search  # noqa: E402
from pa_vfann_exp02.config import load_config  # noqa: E402
from pa_vfann_exp02.exp01_bridge import build_dataset, build_graph  # noqa: E402
from pa_vfann_exp02.ground_truth import build_ground_truth  # noqa: E402
from pa_vfann_exp02.metrics import recall_at_k  # noqa: E402

from common import make_policy  # noqa: E402


def main() -> None:
    config = load_config(ROOT / "config" / "experiment.yaml")
    dataset = build_dataset(config)
    graph = build_graph(dataset, config)
    rows: list[dict] = []
    for policy_type in config["policies"]["types"]:
        for selectivity in config["policies"]["selectivities"]:
            policy = make_policy(config, dataset, policy_type, selectivity)
            gt = build_ground_truth(dataset.query_vectors, dataset.vectors, policy.mask,
                                    int(config["search"]["top_k"]),
                                    int(config["graph"]["chunk_size"]))
            for q in range(dataset.n_queries):
                for budget in (1, 2, 5, 10, 20):
                    outcome = run_search(dataset.query_vectors[q], dataset.vectors, graph,
                                         config, "E3_FIXED_TRACE", budget,
                                         policy_mask=policy.mask, query_id=q)
                    rows.append({
                        "policy_type": policy_type,
                        "selectivity_pct": round(float(selectivity) * 100, 4),
                        "budget": budget,
                        "query_id": q,
                        "recall_at_10": recall_at_k(gt.indices[q], outcome.result_ids),
                        "distance_evaluations": outcome.distance_evaluations,
                        "unique_discovered_nodes": outcome.unique_discovered_nodes,
                        "candidate_transfer_bytes": outcome.candidate_transfer_bytes,
                    })
    df = pd.DataFrame(rows)
    summary = df.groupby(["policy_type", "selectivity_pct", "budget"], as_index=False).agg(
        trials=("recall_at_10", "size"),
        recall_mean=("recall_at_10", "mean"),
        distance_evaluations_mean=("distance_evaluations", "mean"),
        candidate_transfer_bytes_mean=("candidate_transfer_bytes", "mean"),
    )
    out = ROOT / "results" / "tables" / "equal_cost_check.csv"
    summary.to_csv(out, index=False)
    print(f"[equal-cost] wrote {out}")


if __name__ == "__main__":
    main()
