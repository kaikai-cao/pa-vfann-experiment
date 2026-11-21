"""Stage D-1: selectivity x budget x algorithm experiment.

One max-budget run per (query, policy, algorithm) is derived into every
reported budget by exact prefix truncation (see search_common.truncate_outcome).
All E1/E3 plans share the same public traversal per query.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from pa_vfann.baseline_postfilter import adaptive_postfilter_from_plan  # noqa: E402
from pa_vfann.filter_aware import predicate_aware_search  # noqa: E402
from pa_vfann.fixed_trace import fixed_trace_from_plan  # noqa: E402
from pa_vfann.ground_truth import filtered_exact_topk  # noqa: E402
from pa_vfann.search_common import plan_fixed_trace  # noqa: E402

from experiments.exp_common import (  # noqa: E402
    all_budget_outcomes, append_rows, cli_config, make_row, policy_for,
    prepare, result_path,
)


def main() -> None:
    config = cli_config()
    started = time.time()
    dataset, graph, qdist = prepare(config)
    top_k = int(config["search"]["top_k"])
    budgets = [int(v) for v in config["search"]["budgets"]]
    max_budget = max(budgets)
    initial_budget = int(config["search"]["initial_budget"])
    bridge_rs = [int(v) for v in config["search"]["bridge_r_values"]]
    seed = int(config["data"]["seed"])
    nq = dataset.n_queries

    print(f"[selectivity] n={dataset.n} d={dataset.vectors.shape[1]} nq={nq} "
          f"graph_components={graph.connected_components} max_budget={max_budget}", flush=True)

    plans = [plan_fixed_trace(qdist[q], graph, max_budget) for q in range(nq)]
    print(f"[selectivity] public plans ready in {time.time()-started:.1f}s", flush=True)

    rows: list[dict] = []
    for policy_type in config["policies"]["types"]:
        for selectivity in config["policies"]["selectivities"]:
            sigma = float(config["policies"]["clustered_sigma"])
            policy = policy_for(config, dataset, policy_type, selectivity, sigma)
            gt = filtered_exact_topk(qdist, policy.mask, top_k)
            policy_start = time.time()
            for q in range(nq):
                row = qdist[q]
                plan = plans[q]
                e1_full = adaptive_postfilter_from_plan(
                    plan[0], plan[1], plan[2], row, max_budget, policy.mask, top_k,
                    initial_budget, q, graph=graph
                )
                e3_full = fixed_trace_from_plan(plan, row, max_budget, policy.mask, top_k, q)
                e2_full = [
                    predicate_aware_search(
                        row, graph, max_budget, policy.mask, top_k, r, initial_budget, q
                    )
                    for r in bridge_rs
                ]
                insufficient = gt.insufficient(q)
                common = dict(
                    policy_type=policy_type,
                    selectivity=selectivity,
                    sigma=sigma,
                    actual_count=policy.actual_count,
                    actual_selectivity=policy.actual_selectivity,
                    seed=seed,
                )
                for budget in budgets:
                    base = dict(experiment="selectivity", budget=budget, query_id=q,
                                gt_indices=gt.indices[q], insufficient=insufficient, **common)
                    for full in [e1_full, e3_full, *e2_full]:
                        outcome = full if full.budget == budget else None
                        if outcome is None:
                            outcome = truncate_for_budget(full, budget, graph, row, policy.mask, top_k)
                        rows.append(make_row(
                            "selectivity", outcome, base["gt_indices"], insufficient,
                            policy_type, selectivity, sigma, policy.actual_count,
                            policy.actual_selectivity, seed,
                        ))
            print(f"[selectivity] {policy_type} sel={selectivity}: "
                  f"{len(rows)} rows cumulative, {time.time()-policy_start:.1f}s", flush=True)

    append_rows(result_path(config), rows)
    print(f"[selectivity] wrote {len(rows)} rows to {result_path(config)} "
          f"in {time.time()-started:.1f}s", flush=True)


def truncate_for_budget(full, budget, graph, row, mask, top_k):
    from pa_vfann.search_common import truncate_outcome
    return truncate_outcome(full, budget, graph, row, mask, top_k)


if __name__ == "__main__":
    main()
