"""EXP-02A observer audit: who can actually see what?

Reinterprets the frozen EXP-02 leakage CSV under explicit O_server / O_client /
O_network observers. No EXP-02 file is modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

EXP02A = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP02A / "src"))

from pa_vfann_exp02a.audit_data import leakage_rows, load_raw  # noqa: E402
from pa_vfann_exp02a.config import load_config  # noqa: E402
from pa_vfann_exp02a.observers import (  # noqa: E402
    FIELDS, OBSERVERS, output_id_observers, reclassify_leakage_row,
    server_observable_channels, visibility_matrix,
)

SCENARIOS = [
    ("E3_no_feedback_A", "E3_FIXED_TRACE", "A", False, True),
    ("E3_no_feedback_B", "E3_FIXED_TRACE", "B", False, True),
    ("E3_no_feedback_C", "E3_FIXED_TRACE", "C", False, True),
    ("E3_feedback_B", "E3_FIXED_TRACE", "B", True, True),
    ("E1_B", "E1_POSTFILTER", "B", False, True),
    ("E2_B", "E2_BRIDGE", "B", False, True),
    ("E3_no_feedback_B_noTLS", "E3_FIXED_TRACE", "B", False, False),
]


def write(df: pd.DataFrame, name: str) -> None:
    out = EXP02A / "results" / "tables" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[observer] wrote {out.name}: {len(df)} rows")


def main() -> None:
    cfg = load_config()
    raw = load_raw(cfg)
    tls = bool(cfg["protocol"]["network_tls"])

    vis_rows, count_rows = [], []
    for name, algorithm, model, feedback, use_tls in SCENARIOS:
        visible = visibility_matrix(algorithm, model, feedback, use_tls)
        for observer in OBSERVERS:
            seen = [f for f in FIELDS if visible[observer][f]]
            count_rows.append({
                "scenario": name,
                "observer": observer,
                "n_visible_fields": len(seen),
                "visible_fields": "|".join(seen),
                "topk_ids_visible": int(visible[observer]["topk_ids"]),
                "search_trace_visible": int(visible[observer]["search_trace"]),
            })
            for field in FIELDS:
                vis_rows.append({
                    "scenario": name,
                    "observer": observer,
                    "field": field,
                    "visible": int(visible[observer][field]),
                })
    write(pd.DataFrame(vis_rows), "observer_visibility_matrix.csv")
    write(pd.DataFrame(count_rows), "observer_channel_counts.csv")

    channel_rows = []
    for name, algorithm, model, feedback, use_tls in SCENARIOS:
        channels = server_observable_channels(algorithm, feedback)
        channel_rows.append({
            "scenario": name,
            "algorithm": algorithm,
            "model": model,
            "client_feedback_ids": int(feedback),
            "network_tls": int(use_tls),
            "n_server_observable_metrics": len(channels),
            "server_observable_metrics": "|".join(channels),
            "output_id_observers": "+".join(output_id_observers(algorithm, feedback)),
        })
    write(pd.DataFrame(channel_rows), "server_observable_channels.csv")

    lg = leakage_rows(raw)
    rows = []
    for row in lg.to_dict("records"):
        for feedback in (False, True):
            new = reclassify_leakage_row(row, str(row["algorithm"]), feedback)
            rows.append({
                "pair_name": row["pair_name"],
                "budget": int(row["budget"]),
                "algorithm": row["algorithm"],
                "client_feedback_ids": int(feedback),
                "cross_policy_output_distinguishability": new["cross_policy_output_distinguishability"],
                "server_observable_leakage": new["server_observable_leakage"],
                "output_id_observers": new["output_id_observers"],
                "server_can_observe_topk_ids": new["server_can_observe_topk_ids"],
                "legacy_output_id_leakage_renamed": 1,
            })
    reclassified = pd.DataFrame(rows)
    summary = reclassified.groupby(
        ["pair_name", "budget", "algorithm", "client_feedback_ids"],
        as_index=False,
    ).agg(
        n_queries=("cross_policy_output_distinguishability", "size"),
        cross_policy_output_distinguishability_mean=("cross_policy_output_distinguishability", "mean"),
        server_observable_leakage_mean=("server_observable_leakage", "mean"),
        output_id_observers=("output_id_observers", "first"),
        server_can_observe_topk_ids=("server_can_observe_topk_ids", "first"),
    )
    write(summary, "observer_leakage_summary.csv")
    print("[observer] done")


if __name__ == "__main__":
    main()
