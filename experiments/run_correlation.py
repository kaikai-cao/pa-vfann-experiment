"""Stage D-2: authorization-space correlation and trace-leakage experiment.

Part 1 (spatial correlation): at a fixed 10% selection rate, vary the clustered
policy's sigma from tight to diffuse and measure recall/cost for E1/E2/E3.
Part 2 (leakage): for three policy pairs and two budgets, measure four separate
leakage channels for each algorithm. E3 is expected to have zero search-trace
leakage; output leakage is reported separately and is NOT claimed to be hidden.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pa_vfann.baseline_postfilter import adaptive_postfilter, adaptive_postfilter_from_plan  # noqa: E402
from pa_vfann.filter_aware import predicate_aware_search  # noqa: E402
from pa_vfann.fixed_trace import fixed_trace_from_plan, fixed_trace_private_filter  # noqa: E402
from pa_vfann.ground_truth import filtered_exact_topk  # noqa: E402
from pa_vfann.leakage import trace_leakage  # noqa: E402
from pa_vfann.search_common import plan_fixed_trace  # noqa: E402

from experiments.exp_common import (  # noqa: E402
    append_rows, cli_config, make_row, policy_for, prepare, result_path,
)

LEAKAGE_PAIRS = [
    ("random_vs_clustered", ("random", 15.0), ("clustered", 15.0)),
    ("clustered_sigma15_vs_sigma40", ("clustered", 15.0), ("clustered", 40.0)),
    ("random_seed_variants", ("random", 15.0), ("random", 40.0)),
]


def outcomes_for(policy, qdist_row, graph, budget, top_k, initial, bridge_r, query_id):
    return [
        adaptive_postfilter(qdist_row, graph, budget, policy.mask, top_k, initial, query_id),
        predicate_aware_search(qdist_row, graph, budget, policy.mask, top_k, bridge_r, initial, query_id),
        fixed_trace_private_filter(qdist_row, graph, budget, policy.mask, top_k, query_id),
    ]


def main() -> None:
    config = cli_config()
    started = time.time()
    dataset, graph, qdist = prepare(config)
    top_k = int(config["search"]["top_k"])
    budgets = [int(v) for v in config["search"]["budgets"]]
    max_budget = max(budgets)
    initial = int(config["search"]["initial_budget"])
    bridge_r = int(config["search"]["bridge_r_values"][1])
    seed = int(config["data"]["seed"])
    sel = float(config["correlation"]["target_selectivity"])
    nq = dataset.n_queries
    print(f"[correlation] nq={nq} selectivity={sel} bridge_r={bridge_r}", flush=True)

    rows: list[dict] = []
    run_configs: list[tuple[str, float]] = [
        ("clustered", float(s)) for s in config["correlation"]["sigma_values"]
    ] + [("random", float(config["policies"]["clustered_sigma"]))]

    plans = [plan_fixed_trace(qdist[q], graph, max_budget) for q in range(nq)]
    for policy_type, sigma in run_configs:
        policy = policy_for(config, dataset, policy_type, sel, sigma)
        gt = filtered_exact_topk(qdist, policy.mask, top_k)
        for q in range(nq):
            row = qdist[q]
            plan = plans[q]
            e1_full = adaptive_postfilter_from_plan(
                plan[0], plan[1], plan[2], row, max_budget, policy.mask, top_k,
                initial, q, graph=graph
            )
            e3_full = fixed_trace_from_plan(plan, row, max_budget, policy.mask, top_k, q)
            e2_full = predicate_aware_search(row, graph, max_budget, policy.mask, top_k, bridge_r, initial, q)
            for budget in budgets:
                for full in (e1_full, e2_full, e3_full):
                    from pa_vfann.search_common import truncate_outcome
                    outcome = full if full.budget == budget else truncate_outcome(
                        full, budget, graph, row, policy.mask, top_k
                    )
                    rows.append(make_row(
                        "correlation", outcome, gt.indices[q], gt.insufficient(q),
                        policy_type, sel, sigma, policy.actual_count,
                        policy.actual_selectivity, seed,
                    ))
        print(f"[correlation] {policy_type} sigma={sigma} done, rows={len(rows)}", flush=True)

    append_rows(result_path(config), rows)

    # ---- leakage analysis ----
    leakage_rows: list[dict] = []
    leakage_budgets = [int(v) for v in config["correlation"]["leakage_budgets"]]
    for pair_name, (type_a, sigma_a), (type_b, sigma_b) in LEAKAGE_PAIRS:
        policy_a = policy_for(config, dataset, type_a, sel, sigma_a)
        policy_b = policy_for(config, dataset, type_b, sel, sigma_b)
        for budget in leakage_budgets:
            per_query: dict[str, list[dict]] = {"E1_POSTFILTER": [], "E2_BRIDGE": [], "E3_FIXED_TRACE": []}
            for q in range(nq):
                row = qdist[q]
                a_list = outcomes_for(policy_a, row, graph, budget, top_k, initial, bridge_r, q)
                b_list = outcomes_for(policy_b, row, graph, budget, top_k, initial, bridge_r, q)
                for out_a, out_b in zip(a_list, b_list):
                    metrics = trace_leakage(
                        out_a.visited_nodes, out_b.visited_nodes,
                        out_a.stop_position, out_b.stop_position,
                        out_a.result_ids, out_b.result_ids,
                    )
                    per_query[out_a.algorithm].append(metrics)
            for algorithm, values in per_query.items():
                entry = {
                    "policy_pair": pair_name,
                    "algorithm": algorithm,
                    "budget": budget,
                    "selectivity_pct": round(sel * 100, 4),
                    "n_queries": nq,
                    "identical_trace_rate": float(np.mean([
                        abs(v["L_set"]) < 1e-12 and abs(v["L_seq"]) < 1e-12 for v in values
                    ])),
                }
                for key in ("L_set", "L_seq", "stop_position_delta", "returned_count_delta", "L_output_ids"):
                    series = np.asarray([v[key] for v in values], dtype=float)
                    entry[f"{key}_mean"] = float(series.mean())
                    entry[f"{key}_p95"] = float(np.percentile(series, 95))
                leakage_rows.append(entry)
            print(f"[leakage] {pair_name} budget={budget} done", flush=True)

    table = config.path.resolve().parents[1] / "results" / "tables" / "leakage_summary.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(leakage_rows).to_csv(table, index=False)
    print(f"[correlation] wrote {table} and {len(rows)} raw rows in {time.time()-started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
