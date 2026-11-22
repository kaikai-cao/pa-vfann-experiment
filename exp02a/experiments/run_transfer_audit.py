"""EXP-02A transfer-cost audit derived from the frozen EXP-02 raw CSV.

Read-only: no ANN search is executed and no EXP-02 file is written.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

EXP02A = Path(__file__).resolve().parents[1]
ROOT = EXP02A.parent
sys.path.insert(0, str(EXP02A / "src"))

from pa_vfann_exp02a.audit_data import (  # noqa: E402
    candidate_cost_frame, load_raw, recall_target_query_sets,
)
from pa_vfann_exp02a.config import load_config  # noqa: E402
from pa_vfann_exp02a.transfer_models import (  # noqa: E402
    MODELS, MODEL_DESCRIPTIONS, compute_transfer, field_requirements,
)


def write(df: pd.DataFrame, name: str) -> Path:
    out = EXP02A / "results" / "tables" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[transfer] wrote {out.name}: {len(df)} rows")
    return out


def cost_pair(n_mean: float, n_p95: float, model: str, cfg, **params) -> dict:
    c_mean = compute_transfer(int(round(n_mean)), model, cfg, **params)
    c_p95 = compute_transfer(int(math.ceil(n_p95)), model, cfg, **params)
    return {
        "mean_bytes": c_mean.total_bytes,
        "p95_bytes": c_p95.total_bytes,
        "server_to_client_mean_bytes": c_mean.server_to_client_bytes,
        "attribute_request_mean_bytes": c_mean.attribute_request_bytes,
        "attribute_response_mean_bytes": c_mean.attribute_response_bytes,
        "feedback_mean_bytes": c_mean.feedback_bytes,
        "messages": c_mean.messages,
    }


def main() -> None:
    cfg = load_config()
    raw = load_raw(cfg)
    cand = candidate_cost_frame(raw)
    target = float(cfg["analysis"]["target_recall"])
    detail, target_summary = recall_target_query_sets(raw, target)
    write(detail, "recall_target_query_sets_detail.csv")
    write(target_summary, "recall_target_query_sets.csv")

    fields = pd.DataFrame([f.__dict__ for f in field_requirements()])
    fields["model_A_carries_field"] = fields["name"].isin(["candidate_id", "query_distance"])
    write(fields, "candidate_field_requirements.csv")

    base = cfg["attribute_fields"]["baseline"]
    params = dict(acl_bytes=base["acl_bytes"], ttl_bytes=base["ttl_bytes"],
                  extra_bytes=base["extra_bytes"])

    by_model = []
    for row in cand.itertuples(index=False):
        for model in MODELS:
            by_model.append({
                "policy_type": row.policy_type,
                "selectivity_pct": row.selectivity_pct,
                "budget": row.budget,
                "algorithm": "E3_FIXED_TRACE",
                "model": model,
                "description": MODEL_DESCRIPTIONS[model],
                "candidate_count_mean": row.candidate_count_mean,
                "candidate_count_p95": row.candidate_count_p95,
                **cost_pair(row.candidate_count_mean, row.candidate_count_p95,
                            model, cfg, **params),
            })
    write(pd.DataFrame(by_model), "transfer_cost_by_model.csv")

    scan_rows = []
    for attr_total in cfg["attribute_fields"]["total_attribute_scan"]:
        # Only the SUM enters byte accounting; all bytes are assigned to ACL
        # here. This is an explicit scan parameter, not a measured constant.
        scan_params = dict(acl_bytes=int(attr_total), ttl_bytes=0, extra_bytes=0)
        for row in cand.itertuples(index=False):
            for model in ("A", "B", "C"):
                scan_rows.append({
                    "policy_type": row.policy_type,
                    "selectivity_pct": row.selectivity_pct,
                    "budget": row.budget,
                    "model": model,
                    "attribute_record_bytes": int(attr_total),
                    "candidate_count_mean": row.candidate_count_mean,
                    "candidate_count_p95": row.candidate_count_p95,
                    **cost_pair(row.candidate_count_mean, row.candidate_count_p95,
                                model, cfg, **scan_params),
                })
    write(pd.DataFrame(scan_rows), "transfer_cost_by_attribute_size.csv")

    # Cost at the recall target, with BOTH query populations kept separate.
    at_target = target_summary[target_summary["algorithm"] == "E3_FIXED_TRACE"].copy()
    populations = [
        ("cell_mean_all_queries", "budget_cell_mean_reached",
         "candidates_at_cell_mean_reached_all_queries"),
        ("individually_reached_queries", "budget_any_query_reached",
         "candidates_at_any_query_reached_reached_only"),
    ]
    target_rows = []
    for pop_name, budget_col, cand_col in populations:
        for row in at_target.itertuples(index=False):
            budget = getattr(row, budget_col)
            if budget == "NOT_REACHED" or pd.isna(getattr(row, cand_col)):
                continue
            n = float(getattr(row, cand_col))
            for model in MODELS:
                target_rows.append({
                    "policy_type": row.policy_type,
                    "selectivity_pct": row.selectivity_pct,
                    "algorithm": "E3_FIXED_TRACE",
                    "query_population": pop_name,
                    "budget": int(budget),
                    "model": model,
                    "candidate_count_mean": n,
                    "attribute_record_bytes": sum(params.values()),
                    **cost_pair(n, n, model, cfg, **params),
                })
    write(pd.DataFrame(target_rows), "transfer_cost_at_recall_target.csv")
    print("[transfer] done")


if __name__ == "__main__":
    main()
