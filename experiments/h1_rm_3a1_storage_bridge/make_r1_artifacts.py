#!/usr/bin/env python3
"""H1-RM.3A.1-R1: build committed audit subsets, raw hashes and manifest."""
import os
import sys
import json
import hashlib

ROOT = sys.argv[1]
OUT = os.path.join(ROOT, "results", "h1_rm_3a1_r1")
BASE = os.path.join(OUT, "baseline")
BRIDGE = os.path.join(OUT, "bridged")
PARENT = "c7e8189fe60a5d40a5f6aa16b8e0912e0a879e17"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def events_audit(path):
    counts = {}
    for ln in open(path):
        if not ln.strip():
            continue
        o = json.loads(ln)
        key = (o["query_id"], o["group"])
        c = counts.setdefault(key, {"n": 0, "types": {}})
        c["n"] += 1
        t = o["event_type"]
        c["types"][t] = c["types"].get(t, 0) + 1
    return [{"query_id": q, "group": g, "event_count": c["n"], "by_type": c["types"]}
            for (q, g), c in sorted(counts.items())]


def requests_audit(path, limit=6):
    rows = []
    seen = {}
    for ln in open(path):
        if not ln.strip():
            continue
        o = json.loads(ln)
        key = (o["query_id"], o["group"])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= limit:
            rows.append(o)
    return rows


# audit subsets
ea = events_audit(os.path.join(BASE, "events.jsonl"))
with open(os.path.join(OUT, "events_audit.jsonl"), "w") as f:
    for r in ea:
        f.write(json.dumps(r) + "\n")
ra = requests_audit(os.path.join(BRIDGE, "requests.jsonl"))
with open(os.path.join(OUT, "requests_audit.jsonl"), "w") as f:
    for r in ra:
        f.write(json.dumps(r) + "\n")

# raw hashes of every log (including gitignored full logs)
raw = {}
for sub in ("baseline", "bridged"):
    for name in ("events.jsonl", "topk.jsonl", "run_summary.jsonl", "requests.jsonl"):
        p = os.path.join(OUT, sub, name)
        if os.path.exists(p):
            raw[f"{sub}_{name}_sha256"] = sha256(p)
with open(os.path.join(OUT, "raw_hashes.json"), "w") as f:
    json.dump(raw, f, indent=2)
    f.write("\n")

# manifest
committed = [
    "docs/H1_RM_3A_1_R1_EXTERNAL_LABEL_READ_BOUNDARY.md",
    "experiments/h1_rm_3a1_storage_bridge/storage_access.h",
    "experiments/h1_rm_3a1_storage_bridge/hnswlib_bridge/hnswalg.h",
    "experiments/h1_rm_3a1_storage_bridge/main.cpp",
    "experiments/h1_rm_3a1_storage_bridge/verify_r1.py",
    "experiments/h1_rm_3a1_storage_bridge/make_r1_artifacts.py",
    "results/h1_rm_3a1_r1/verification.json",
    "results/h1_rm_3a1_r1/events_audit.jsonl",
    "results/h1_rm_3a1_r1/requests_audit.jsonl",
    "results/h1_rm_3a1_r1/raw_hashes.json",
    "results/h1_rm_3a1_r1/baseline/topk.jsonl",
    "results/h1_rm_3a1_r1/baseline/run_summary.jsonl",
    "results/h1_rm_3a1_r1/baseline/requests.jsonl",  # empty: bridge=0 emits no requests
    "results/h1_rm_3a1_r1/bridged/topk.jsonl",
    "results/h1_rm_3a1_r1/bridged/run_summary.jsonl",
    "results/h1_rm_3a1_r1/manifest.json",
]
manifest = {
    "task": "H1-RM.3A.1-R1 External Label Read Boundary Closure",
    "parent_commit": PARENT,
    "small_scale": {"queries": 5, "groups": ["C0", "C1", "C2"]},
    "config": "identical to frozen EXP-10A/H1-RM.3A.1 (N=1000, dim=16, IP, M=16, efC=200, efS=64, k=10, seed=2026, label=100000+17*i)",
    "committed_files": committed,
    "raw_logs_gitignored": [
        "results/h1_rm_3a1_r1/baseline/events.jsonl",
        "results/h1_rm_3a1_r1/bridged/events.jsonl",
        "results/h1_rm_3a1_r1/bridged/requests.jsonl",
    ],
    "raw_hashes": raw,
}
with open(os.path.join(OUT, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
print("events_audit rows=%d requests_audit rows=%d" % (len(ea), len(ra)))
print("manifest committed_files=%d" % len(committed))
