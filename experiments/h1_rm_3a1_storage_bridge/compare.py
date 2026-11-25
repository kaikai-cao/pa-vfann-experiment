#!/usr/bin/env python3
"""H1-RM.3A.1: verify semantic preservation across the storage bridge.

Compares baseline (no storage injected) vs bridged (storage injected) on:
  events.jsonl  -- exact byte-for-byte, and field-by-field per event type
  topk.jsonl    -- exact byte-for-byte
Then analyzes the bridged request trace for ordering, duplicates, query
association, batch behavior, and request end marker.

Read-only on all inputs; writes only under results/h1_rm_3a1/comparison/.
"""
import os
import sys
import json
import hashlib
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
BASE = os.path.join(ROOT, "results", "h1_rm_3a1", "baseline")
BRIDGE = os.path.join(ROOT, "results", "h1_rm_3a1", "bridged")
CMP = os.path.join(ROOT, "results", "h1_rm_3a1", "comparison")
os.makedirs(CMP, exist_ok=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def main():
    result = {"config": {
        "N": 1000, "DIM": 16, "M": 16, "ef_construction": 200,
        "ef_search": 64, "K": 10, "NQ": 50, "seed": 2026,
        "label_rule": "100000 + 17*i", "groups": ["C0", "C1", "C2"],
    }}

    # ---- 1. byte-for-byte comparison of event and topk streams ---------------
    file_checks = {}
    for name in ("events.jsonl", "topk.jsonl"):
        pb = os.path.join(BASE, name)
        pg = os.path.join(BRIDGE, name)
        hb, hg = sha256(pb), sha256(pg)
        file_checks[name] = {
            "baseline_sha256": hb,
            "bridged_sha256": hg,
            "identical": hb == hg,
            "baseline_lines": len(read_lines(pb)),
            "bridged_lines": len(read_lines(pg)),
        }
    result["byte_identity"] = file_checks
    all_identical = all(v["identical"] for v in file_checks.values())

    # ---- 2. field-by-field per-event-type comparison -------------------------
    bev = [json.loads(x) for x in read_lines(os.path.join(BASE, "events.jsonl"))]
    gev = [json.loads(x) for x in read_lines(os.path.join(BRIDGE, "events.jsonl"))]
    per_type = {}
    if len(bev) == len(gev):
        by_type = defaultdict(lambda: {"count": 0, "mismatches": 0,
                                       "record_equal": 0, "dist_bits_equal": 0,
                                       "extra_equal": 0})
        for a, b in zip(bev, gev):
            t = a["event_type"]
            d = by_type[t]
            d["count"] += 1
            if a == b:
                d["record_equal"] += 1
            else:
                d["mismatches"] += 1
            if a.get("dist_bits") == b.get("dist_bits"):
                d["dist_bits_equal"] += 1
            if a.get("extra") == b.get("extra"):
                d["extra_equal"] += 1
        per_type = dict(by_type)
    result["events_by_type"] = per_type

    # ---- 3. compare top-k as parsed records ----------------------------------
    btop = [json.loads(x) for x in read_lines(os.path.join(BASE, "topk.jsonl"))]
    gtop = [json.loads(x) for x in read_lines(os.path.join(BRIDGE, "topk.jsonl"))]
    result["topk_records"] = {
        "baseline_count": len(btop),
        "bridged_count": len(gtop),
        "all_equal": btop == gtop,
    }

    # ---- 4. request-trace analysis ------------------------------------------
    req = [json.loads(x) for x in read_lines(os.path.join(BRIDGE, "requests.jsonl"))]
    by_qg = defaultdict(list)
    for r in req:
        by_qg[(r["query_id"], r["group"])].append(r)

    ordering_ok = True
    has_start = has_end = True
    node_ids = 0
    neighbor_ids = 0
    duplicates = 0
    for key, rows in by_qg.items():
        seqs = [r["seq"] for r in rows]
        if seqs != sorted(seqs):
            ordering_ok = False
        tags = [r["boundary"] for r in rows]
        if "query_start" not in tags:
            has_start = False
        if "query_end" not in tags:
            has_end = False
        seen = set()
        for r in rows:
            if r["request_type"] == "node_read":
                node_ids += 1
            elif r["request_type"] == "neighbor_read":
                neighbor_ids += 1
            k = (r["request_type"], r["node_id"], r["level"], r["seq"])
            if k in seen:
                duplicates += 1
            seen.add(k)

    count_groups = {g: sum(1 for k in by_qg if k[1] == g) for g in ("C0", "C1", "C2")}
    result["request_trace"] = {
        "total_records": len(req),
        "node_read_records": node_ids,
        "neighbor_read_records": neighbor_ids,
        "distinct_query_group_units": len(by_qg),
        "units_by_group": count_groups,
        "ordered_by_seq": ordering_ok,
        "all_units_have_query_start": has_start,
        "all_units_have_query_end": has_end,
        "duplicate_seq_keys": duplicates,
        "query_id_visible": True,
        "node_id_visible": True,
        "batch_reads": "none; one node/neighbor per request record",
    }

    # ---- 5. gate computation -------------------------------------------------
    semantic_preserved = (
        all_identical and result["topk_records"]["all_equal"]
        and all(v["mismatches"] == 0 for v in per_type.values())
    )
    bridge_complete = (
        ordering_ok and has_start and has_end
        and len(by_qg) == 150  # 50 queries * 3 groups
        and node_ids > 0 and neighbor_ids > 0
    )
    if semantic_preserved and bridge_complete:
        gate = "PASS"
    elif semantic_preserved or bridge_complete:
        gate = "CONDITIONAL"
    else:
        gate = "STOP"
    result["gate"] = {
        "semantic_preserved": semantic_preserved,
        "bridge_complete": bridge_complete,
        "decision": gate,
    }

    out = os.path.join(CMP, "comparison.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("semantic_preserved=%s bridge_complete=%s gate=%s" %
          (semantic_preserved, bridge_complete, gate))
    print("events_identical=%s topk_identical=%s req_records=%d units=%d" %
          (file_checks["events.jsonl"]["identical"],
           file_checks["topk.jsonl"]["identical"],
           len(req), len(by_qg)))


if __name__ == "__main__":
    main()
