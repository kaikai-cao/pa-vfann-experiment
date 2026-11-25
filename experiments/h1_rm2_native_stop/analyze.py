#!/usr/bin/env python3
"""H1-RM.2 analysis: verify C0/C1/C2 semantics and emit summary + manifest.

Reads results/h1_rm2/{trace_on,trace_off,upstream}/*.jsonl (all read-only here)
and writes results/h1_rm2/{summary.csv,gate.json,manifest.json}.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

SITE_TYPES = ["distance_eval", "candidate_pop", "candidate_consider",
              "filter_check", "result_add", "result_remove", "stop_check", "search_stop"]


def fnv1a(parts) -> str:
    h = 14695981039346656037
    for p in parts:
        for c in str(p):
            h ^= ord(c)
            h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return format(h, "016x")

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results" / "h1_rm2"
LABEL_BASE, LABEL_STEP = 100000, 17


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(sub: str, name: str) -> pd.DataFrame:
    with open(BASE / sub / name, encoding="utf-8") as f:
        return pd.DataFrame([json.loads(line) for line in f if line.strip()])


def topk_pivot(sub: str) -> pd.DataFrame:
    t = load(sub, "topk.jsonl")
    t["mapped_id"] = t["external_id"]
    m = t["group"] != "C0"
    t.loc[m, "mapped_id"] = LABEL_BASE + LABEL_STEP * t.loc[m, "external_id"]
    return t.pivot_table(
        index=["query_id", "rank"], columns="group",
        values=["mapped_id", "dist_bits"], aggfunc="first",
    )


def main() -> int:
    checks: dict[str, bool] = {}
    metrics: dict[str, object] = {}

    top = topk_pivot("trace_on")
    n_cells = len(top)
    checks["c0_c1_top10_count"] = n_cells == 500
    checks["c0_c1_top10_external_id"] = bool(
        (top[("mapped_id", "C0")] == top[("mapped_id", "C1")]).all()
    )
    checks["c0_c1_top10_float32_bits"] = bool(
        (top[("dist_bits", "C0")] == top[("dist_bits", "C1")]).all()
    )
    metrics["c0_c1_top10_cells"] = int(n_cells)
    metrics["c0_c1_top10_id_matches"] = int(
        (top[("mapped_id", "C0")] == top[("mapped_id", "C1")]).sum()
    )
    metrics["c0_c1_top10_bits_matches"] = int(
        (top[("dist_bits", "C0")] == top[("dist_bits", "C1")]).sum()
    )

    # three independent channels must agree on top-k for every group
    ch = {"on": topk_pivot("trace_on"), "off": topk_pivot("trace_off"),
          "up": topk_pivot("upstream")}
    for g in ("C0", "C1", "C2"):
        checks[f"topk_channels_identical_{g}"] = bool(
            (ch["on"][("mapped_id", g)] == ch["off"][("mapped_id", g)]).all()
            and (ch["on"][("mapped_id", g)] == ch["up"][("mapped_id", g)]).all()
            and (ch["on"][("dist_bits", g)] == ch["off"][("dist_bits", g)]).all()
            and (ch["on"][("dist_bits", g)] == ch["up"][("dist_bits", g)]).all()
        )

    events = load("trace_on", "events.jsonl")

    # ---- compact audit file (the full 67MB event log is gitignored) --------
    # One record per (query, group): per-site counts + a canonical FNV-1a hash
    # of the distance_eval sequence (internal_id, dist_bits, level triples).
    # For C2 additionally store every event strictly inside the
    # (K-hit, search_stop) window, which is the object of study.
    audit_rows = []
    s_on_full = load("trace_on", "run_summary.jsonl")
    rsum = {(int(r.query_id), r.group): r for r in s_on_full.itertuples()}
    for (qid, grp), g in events.groupby(["query_id", "group"]):
        g = g.sort_values("event_index")
        rec = {"query_id": int(qid), "group": grp,
               "event_count": int(len(g))}
        for t in SITE_TYPES:
            rec["n_" + t] = int((g["event_type"] == t).sum())
        de = g[g["event_type"] == "distance_eval"]
        rec["distance_eval_hash"] = fnv1a(
            zip(de["internal_id"].tolist(), de["dist_bits"].tolist(), de["level"].tolist())
        )
        if grp == "C2":
            r = rsum[(int(qid), "C2")]
            mid = g[(g["event_index"] > r.khit_event_index) &
                    (g["event_index"] < r.first_search_stop_index)]
            rec["gap_events"] = [
                {"event_index": int(e.event_index), "event_type": e.event_type,
                 "internal_id": int(e.internal_id), "dist_bits": e.dist_bits}
                for e in mid.itertuples()
            ]
        audit_rows.append(rec)
    with open(BASE / "events_audit.jsonl", "w", encoding="utf-8") as f:
        for r in sorted(audit_rows, key=lambda x: (x["query_id"], x["group"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    s_on = load("trace_on", "run_summary.jsonl")
    s_off = load("trace_off", "run_summary.jsonl")
    s_up = load("upstream", "run_summary.jsonl")

    checks["sink_off_no_events"] = len(load("trace_off", "events.jsonl")) == 0 and bool(
        (s_off["event_count"] == 0).all()
    )
    checks["upstream_no_events"] = len(load("upstream", "events.jsonl")) == 0 and bool(
        (s_up["event_count"] == 0).all()
    )
    checks["group_count_150"] = len(s_on) == 150 and s_on["query_id"].nunique() == 50
    checks["event_count_consistent"] = bool(
        events.groupby(["query_id", "group"]).size().sum() == s_on["event_count"].sum()
    )

    # C0 vs C1: identical event sequence (distance_eval / all sites)
    de = events[events["event_type"] == "distance_eval"]
    c0 = de[de["group"] == "C0"].sort_values(["query_id", "event_index"]).reset_index(drop=True)
    c1 = de[de["group"] == "C1"].sort_values(["query_id", "event_index"]).reset_index(drop=True)
    checks["c0_c1_dist_eval_len_equal"] = len(c0) == len(c1)
    if len(c0) == len(c1):
        checks["c0_c1_dist_eval_seq_identical"] = bool(
            (c0["internal_id"].values == c1["internal_id"].values).all()
            and (c0["dist_bits"].values == c1["dist_bits"].values).all()
            and (c0["level"].values == c1["level"].values).all()
        )
    metrics["c0_c1_distance_eval_events_each"] = int(len(c0))

    cnt = events.groupby(["group", "event_type"]).size().unstack(fill_value=0)
    site_types = ["distance_eval", "candidate_pop", "candidate_consider",
                  "filter_check", "result_add", "result_remove", "stop_check", "search_stop"]
    checks["all_eight_event_types_present"] = all(t in cnt.columns for t in site_types)
    checks["c0_c1_event_counts_identical"] = bool(
        (cnt.loc["C0", site_types] == cnt.loc["C1", site_types]).all()
    )

    # C2 boundary
    c2 = s_on[s_on["group"] == "C2"].copy()
    checks["c2_khit_count_accurate"] = bool((c2["auth_hits"] == c2["n_filter_ok"]).all())
    checks["c2_one_stop_per_query"] = bool((c2["n_search_stop"] == 1).all())
    checks["c2_khit_before_stop"] = bool(
        ((c2["khit_event_index"] >= 0) &
         (c2["first_search_stop_index"] > c2["khit_event_index"])).all()
    )
    c2["gap"] = c2["first_search_stop_index"] - c2["khit_event_index"]
    metrics["c2_gap_mean"] = float(c2["gap"].mean())
    metrics["c2_gap_min"] = int(c2["gap"].min())
    metrics["c2_gap_max"] = int(c2["gap"].max())
    metrics["c2_auth_hits_min"] = int(c2["auth_hits"].min())
    metrics["c2_auth_hits_max"] = int(c2["auth_hits"].max())
    metrics["c2_returned_size_min"] = int(c2["returned_size"].min())
    metrics["c2_returned_size_max"] = int(c2["returned_size"].max())
    metrics["c0_returned_size"] = int(s_on[s_on["group"] == "C0"]["returned_size"].iloc[0])
    metrics["c1_returned_size"] = int(s_on[s_on["group"] == "C1"]["returned_size"].iloc[0])

    gap_mid = {t: 0 for t in site_types}
    for q in range(50):
        g = events[(events["group"] == "C2") & (events["query_id"] == q)]
        row = c2[c2["query_id"] == q].iloc[0]
        mid = g[(g["event_index"] > row["khit_event_index"]) &
                (g["event_index"] < row["first_search_stop_index"])]
        vc = mid["event_type"].value_counts()
        for t in site_types:
            gap_mid[t] += int(vc.get(t, 0))
    metrics["c2_events_between_khit_and_stop"] = gap_mid

    # authoritative C2 finding: stop is NOT at K-hit, it is at the next
    # candidate_set-loop boundary; K-hit changes the observable control flow.
    checks["c2_stop_boundary_lag_positive"] = bool((c2["gap"] > 0).all())

    gate = "PASS" if all(checks.values()) else "FAIL"
    (BASE / "gate.json").write_text(
        json.dumps({"decision": gate, "checks": checks, "metrics": metrics},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # summary.csv: per group event counts + returned size
    rows = []
    for (grp, qid), g in events.groupby(["group", "query_id"]):
        pass
    ssum = s_on.groupby("group").agg(
        queries=("query_id", "nunique"),
        mean_returned_size=("returned_size", "mean"),
        mean_auth_hits=("auth_hits", "mean"),
        mean_event_count=("event_count", "mean"),
    ).reset_index()
    ssum.to_csv(BASE / "summary.csv", index=False)

    # manifest: pin all inputs/outputs + config.
    # The full 67MB event log is gitignored; its hash is recorded separately
    # so a local rebuild can be verified, while the committed audit file
    # (events_audit.jsonl) is sufficient to re-run every pytest gate check.
    files_to_pin = [
        "events_audit.jsonl",
        "trace_on/topk.jsonl", "trace_on/run_summary.jsonl",
        "trace_off/topk.jsonl", "trace_off/run_summary.jsonl",
        "upstream/topk.jsonl", "upstream/run_summary.jsonl",
        "gate.json", "summary.csv",
    ]
    manifest = {
        "task": "H1-RM.2 Native HNSW Filter/Stop Semantics",
        "baseline_exp10a_commit": "68ed142a234428bafc85be5cbad8de12371688f2",
        "upstream_hnswlib_commit": "d9b3608c83d83b46c96e25088cb1d729b29dcfe9",
        "config": {"N": 1000, "dim": 16, "space": "inner_product", "M": 16,
                   "ef_construction": 200, "ef_search": 64, "ef_rule": 64,
                   "k": 10, "queries": 50, "seed": 2026,
                   "label_base": 100000, "label_step": 17,
                   "authorized_nodes": 100, "auth_rule": "hash(label)*odd >>15 %100 <10"},
        "groups": {
            "C0": "searchKnn(q,10,filter) standard path, ef=max(ef_,k)=64",
            "C1": "searchStopConditionClosest + EfReplayStopCondition (ef=64, real result set)",
            "C2": "C1 + K-hit stop (K=10 authorized filter passes)",
        },
        "decision": gate,
        "checks": checks,
        "metrics": metrics,
        "files": {p: sha256_file(BASE / p) for p in files_to_pin if (BASE / p).exists()},
        "full_event_log": {
            "path": "trace_on/events.jsonl",
            "sha256": sha256_file(BASE / "trace_on" / "events.jsonl"),
            "lines": int(s_on["event_count"].sum()),
            "gitignored": True,
            "note": "Full 428107-event raw log; regenerate via build_and_run.sh. "
                    "events_audit.jsonl is the committed, sufficient audit subset.",
        },
        "source_hashes": {
            "pristine_hnswalg": sha256_file(
                ROOT / "third_party/hnswlib-v0.9.0/hnswlib/hnswalg.h"),
            "rm2_hnswalg": sha256_file(
                ROOT / "third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/hnswalg.h"),
            "rm2_sink": sha256_file(
                ROOT / "third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/rm2_sink.h"),
        },
    }
    (BASE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("decision=" + gate)
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'} {k}")
    print("metrics=" + json.dumps(metrics, ensure_ascii=False))
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
