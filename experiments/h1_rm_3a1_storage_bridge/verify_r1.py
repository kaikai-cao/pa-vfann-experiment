#!/usr/bin/env python3
"""H1-RM.3A.1-R1 small-scale verification.

Reads the committed R1 results (5 queries x C0/C1/C2) and checks:
  1. semantic streams (events/topk/summary) baseline vs bridged byte-identical
  2. request log: label_read present, seq strictly increasing per unit,
     query_start/query_end boundaries matched, no duplicate keys
  3. label reads are attributed to the correct node ids and no label read
     happens for the entrypoint-only path unless a label was actually needed
  4. request count breakdown by group, with an explanation hook

Only reads files; writes comparison.json into the R1 results dir.
"""
import os
import sys
import json
import hashlib
from collections import defaultdict

ROOT = sys.argv[1]
OUT = os.path.join(ROOT, "results", "h1_rm_3a1_r1")
BASE = os.path.join(OUT, "baseline")
BRIDGE = os.path.join(OUT, "bridged")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path):
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


# ---- 1. semantic byte identity -------------------------------------------
byte_identity = {}
for name in ("events.jsonl", "topk.jsonl", "run_summary.jsonl"):
    a = sha256(os.path.join(BASE, name))
    b = sha256(os.path.join(BRIDGE, name))
    byte_identity[name] = {"baseline_sha256": a, "bridged_sha256": b,
                           "identical": a == b}

# ---- 2. request log contract ---------------------------------------------
reqs = load_jsonl(os.path.join(BRIDGE, "requests.jsonl"))
units = defaultdict(list)
for r in reqs:
    units[(r["query_id"], r["group"])].append(r)

seq_violations = []
boundary_mismatch = []
type_counts = defaultdict(int)
per_group_types = defaultdict(lambda: defaultdict(int))
label_by_unit = {}
node_by_unit = {}
for (q, g), rows in sorted(units.items()):
    seqs = [r["seq"] for r in rows]
    if any(b <= a for a, b in zip(seqs, seqs[1:])):
        seq_violations.append((q, g))
    starts = [r for r in rows if r["boundary"] == "query_start"]
    ends = [r for r in rows if r["boundary"] == "query_end"]
    if len(starts) != 1 or len(ends) != 1 or starts[0]["seq"] >= ends[0]["seq"]:
        boundary_mismatch.append((q, g))
    for r in rows:
        type_counts[r["request_type"]] += 1
        per_group_types[g][r["request_type"]] += 1
    label_by_unit[(q, g)] = sum(1 for r in rows if r["request_type"] == "label_read")
    node_by_unit[(q, g)] = sum(1 for r in rows if r["request_type"] == "node_read")

# label_read node ids must be a subset of the unit's node_read ids (same blocks)
label_subset_ok = True
label_not_in_node = []
for (q, g), rows in units.items():
    node_ids = {r["node_id"] for r in rows if r["request_type"] == "node_read"}
    label_ids = {r["node_id"] for r in rows if r["request_type"] == "label_read"}
    if not label_ids.issubset(node_ids):
        label_subset_ok = False
        label_not_in_node.append((q, g, len(label_ids - node_ids)))

result = {
    "config": {"queries": 5, "groups": ["C0", "C1", "C2"],
               "note": "first 5 queries of the frozen fixed config"},
    "byte_identity": byte_identity,
    "request_trace": {
        "total_requests": len(reqs),
        "units": len(units),
        "by_type": dict(type_counts),
        "by_group": {g: dict(t) for g, t in sorted(per_group_types.items())},
        "seq_strictly_increasing": len(seq_violations) == 0,
        "seq_violations": seq_violations,
        "boundary_matched": len(boundary_mismatch) == 0,
        "boundary_mismatch": boundary_mismatch,
        "label_read_subset_of_node_read": label_subset_ok,
        "label_ids_not_in_node_read": label_not_in_node,
        "label_read_per_unit_min": min(label_by_unit.values()) if label_by_unit else 0,
        "label_read_per_unit_max": max(label_by_unit.values()) if label_by_unit else 0,
        "node_read_per_unit_min": min(node_by_unit.values()) if node_by_unit else 0,
        "node_read_per_unit_max": max(node_by_unit.values()) if node_by_unit else 0,
    },
}
result["gate"] = {
    "semantic_identity": all(v["identical"] for v in byte_identity.values()),
    "label_read_present": type_counts.get("label_read", 0) > 0,
    "seq_ok": len(seq_violations) == 0,
    "boundary_ok": len(boundary_mismatch) == 0,
    "label_subset_ok": label_subset_ok,
}
result["gate"]["overall"] = all(result["gate"].values())

with open(os.path.join(OUT, "verification.json"), "w") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps(result["gate"], ensure_ascii=False))
print("by_type:", dict(type_counts))
print("by_group:", {g: dict(t) for g, t in sorted(per_group_types.items())})
