"""EXP-02 selectivity experiment (no global distance oracle)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "src"))

from pa_vfann_exp02.algorithms import derive, run_log
from pa_vfann_exp02.config import load_config
from pa_vfann_exp02.exp01_bridge import build_dataset, build_graph
from pa_vfann_exp02.ground_truth import build_ground_truth

from common import FIELDS, append_rows, cli_config, make_policy, outcome_row, result_path, variants


def main() -> None:
    config, explicit_output = cli_config()
    out = result_path(config, explicit_output)
    if out.exists():
        import pandas as pd

        existing = pd.read_csv(out)
        existing = existing[existing["experiment"] != "selectivity"]
        existing.reindex(columns=FIELDS).to_csv(out, index=False)  # preserve other experiments
    dataset = build_dataset(config)
    graph = build_graph(dataset, config)
    seed = int(config["data"]["seed"])
    budgets = [int(b) for b in config["search"]["budgets"]]
    max_budget = max(budgets)
    sigma = float(config["policies"]["clustered_sigma"])
    n_queries = dataset.n_queries
    rows: list[dict] = []
    total = 0

    for policy_type in config["policies"]["types"]:
        for selectivity in config["policies"]["selectivities"]:
            policy = make_policy(config, dataset, policy_type, selectivity)
            gt = build_ground_truth(
                dataset.query_vectors, dataset.vectors, policy.mask,
                int(config["search"]["top_k"]), int(config["graph"]["chunk_size"]),
            )
            print(f"[selectivity] {policy_type} {selectivity:.0%}: authorized={policy.actual_count}", flush=True)
            for q in range(n_queries):
                for algorithm, bridge_r in variants(config):
                    log = run_log(
                        dataset.query_vectors[q], dataset.vectors, graph, config, algorithm,
                        policy_mask=policy.mask, bridge_r=bridge_r, max_expansions=max_budget,
                    )
                    for budget in budgets:
                        outcome = derive(log, config, budget, policy_mask=policy.mask, query_id=q)
                        rows.append(outcome_row(
                            "selectivity", outcome, gt.indices[q], policy_type, selectivity, sigma,
                            gt.insufficient(q), policy.actual_count, policy.actual_selectivity, seed,
                        ))
                        total += 1
                if len(rows) >= 4000:
                    append_rows(out, rows)
                    rows.clear()
    append_rows(out, rows)
    print(f"[selectivity] wrote {total} rows to {out}", flush=True)


if __name__ == "__main__":
    main()
