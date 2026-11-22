"""EXP-02 policy-pair leakage experiment (traces, stop, output channels)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "src"))

from pa_vfann_exp02.algorithms import derive, run_log
from pa_vfann_exp02.config import load_config
from pa_vfann_exp02.exp01_bridge import (
    build_dataset, build_graph, normalized_edit_distance, set_leakage,
)

from common import append_rows, cli_config, make_policy, outcome_row, result_path


def sha(seq) -> str:
    return hashlib.sha256(",".join(str(v) for v in seq).encode("ascii")).hexdigest()[:16]


def ids_text(outcome) -> str:
    return ",".join("None" if v is None else str(v) for v in outcome.result_ids)


def main() -> None:
    config, explicit_output = cli_config()
    out = result_path(config, explicit_output)
    dataset = build_dataset(config)
    graph = build_graph(dataset, config)
    seed = int(config["data"]["seed"])
    budgets = [int(b) for b in config["correlation"]["leakage_budgets"]]
    max_budget = max(int(b) for b in config["search"]["budgets"])
    r_values = config["search"]["bridge_r_values"]
    bridge_r = int(r_values[len(r_values) // 2]) if r_values else 2
    sigma = float(config["policies"]["clustered_sigma"])
    algorithms = ["E1_POSTFILTER", "E2_BRIDGE", "E3_FIXED_TRACE"]
    rows: list[dict] = []
    total = 0

    for spec in config["correlation"]["leakage_pairs"]:
        name, dist_a, sel_a, dist_b, sel_b = spec
        sel_a, sel_b = float(sel_a), float(sel_b)
        policy_a = make_policy(config, dataset, dist_a, sel_a)
        policy_b = make_policy(config, dataset, dist_b, sel_b)
        print(f"[leakage] {name}: A={policy_a.actual_count} B={policy_b.actual_count}", flush=True)
        for q in range(dataset.n_queries):
            for algorithm in algorithms:
                r = bridge_r if algorithm == "E2_BRIDGE" else None
                log_a = run_log(
                    dataset.query_vectors[q], dataset.vectors, graph, config, algorithm,
                    policy_mask=policy_a.mask if algorithm != "E3_FIXED_TRACE" else None,
                    bridge_r=r, max_expansions=max_budget,
                )
                log_b = run_log(
                    dataset.query_vectors[q], dataset.vectors, graph, config, algorithm,
                    policy_mask=policy_b.mask if algorithm != "E3_FIXED_TRACE" else None,
                    bridge_r=r, max_expansions=max_budget,
                )
                for budget in budgets:
                    oa = derive(log_a, config, budget, policy_mask=policy_a.mask, query_id=q)
                    ob = derive(log_b, config, budget, policy_mask=policy_b.mask, query_id=q)
                    row = outcome_row(
                        "leakage", oa, (), f"{dist_a}_vs_{dist_b}", sel_a, sigma,
                        False, policy_a.actual_count, policy_a.actual_selectivity, seed,
                    )
                    row.update({
                        "pair_name": name,
                        "policy_a": f"{dist_a}_{sel_a:g}",
                        "policy_b": f"{dist_b}_{sel_b:g}",
                        "discovery_leakage": set_leakage(oa.discovery_sequence, ob.discovery_sequence),
                        "visit_leakage": set_leakage(oa.visit_sequence, ob.visit_sequence),
                        "expansion_leakage": set_leakage(oa.expansion_sequence, ob.expansion_sequence),
                        "visit_edit_leakage": normalized_edit_distance(oa.visit_sequence, ob.visit_sequence),
                        "stop_position_delta": abs(oa.stop_position - ob.stop_position),
                        "candidate_count_delta": abs(oa.candidate_count - ob.candidate_count),
                        "returned_count_delta": abs(oa.returned_count - ob.returned_count),
                        "output_id_leakage": set_leakage(oa.result_ids, ob.result_ids),
                        "identical_discovery": int(oa.discovery_sequence == ob.discovery_sequence),
                        "identical_visit": int(oa.visit_sequence == ob.visit_sequence),
                        "identical_expansion": int(oa.expansion_sequence == ob.expansion_sequence),
                        "discovery_sha_a": sha(oa.discovery_sequence),
                        "discovery_sha_b": sha(ob.discovery_sequence),
                        "returned_ids_a": ids_text(oa),
                        "returned_ids_b": ids_text(ob),
                        "recall_at_10": "", "gt_size": 0, "insufficient_gt": 0,
                    })
                    rows.append(row)
                    total += 1
                if len(rows) >= 2000:
                    append_rows(out, rows)
                    rows.clear()
    append_rows(out, rows)
    print(f"[leakage] wrote {total} rows to {out}", flush=True)


if __name__ == "__main__":
    main()
