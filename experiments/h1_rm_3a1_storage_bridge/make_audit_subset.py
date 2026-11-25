#!/usr/bin/env python3
"""Create committed audit subsets from the large raw logs (regenerable)."""
import os, sys, json, hashlib
ROOT = sys.argv[1]
OUT = os.path.join(ROOT, "results", "h1_rm_3a1")

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1<<20), b""): h.update(c)
    return h.hexdigest()

def events_audit(path):
    rows = []
    counts = {}
    with open(path) as f:
        for ln in f:
            if not ln.strip(): continue
            o = json.loads(ln)
            key = (o["query_id"], o["group"])
            c = counts.setdefault(key, {"n":0,"types":{},"ids":[]})
            c["n"] += 1
            t = o["event_type"]; c["types"][t] = c["types"].get(t,0)+1
            if len(c["ids"]) < 8: c["ids"].append(o["internal_id"])
    for (q,g),c in sorted(counts.items()):
        rows.append({"query_id":q,"group":g,"event_count":c["n"],
                     "by_type":c["types"],"first_internal_ids":c["ids"]})
    return rows

def requests_audit(path, limit=6):
    rows = []
    seen = {}
    with open(path) as f:
        for ln in f:
            if not ln.strip(): continue
            o = json.loads(ln)
            key = (o["query_id"], o["group"])
            seen[key] = seen.get(key,0)+1
            if seen[key] <= limit: rows.append(o)
    return rows

# events audit (baseline; bridged is byte-identical so one subset suffices)
ea = events_audit(os.path.join(OUT,"baseline","events.jsonl"))
with open(os.path.join(OUT,"events_audit.jsonl"),"w") as f:
    for r in ea: f.write(json.dumps(r)+"\n")
# requests audit subset
ra = requests_audit(os.path.join(OUT,"bridged","requests.jsonl"))
with open(os.path.join(OUT,"requests_audit.jsonl"),"w") as f:
    for r in ra: f.write(json.dumps(r)+"\n")
# raw hashes
raw = {
 "baseline_events_sha256": sha256(os.path.join(OUT,"baseline","events.jsonl")),
 "bridged_events_sha256": sha256(os.path.join(OUT,"bridged","events.jsonl")),
 "bridged_requests_sha256": sha256(os.path.join(OUT,"bridged","requests.jsonl")),
 "baseline_topk_sha256": sha256(os.path.join(OUT,"baseline","topk.jsonl")),
 "bridged_topk_sha256": sha256(os.path.join(OUT,"bridged","topk.jsonl")),
 "baseline_summary_sha256": sha256(os.path.join(OUT,"baseline","run_summary.jsonl")),
 "bridged_summary_sha256": sha256(os.path.join(OUT,"bridged","run_summary.jsonl")),
}
with open(os.path.join(OUT,"raw_hashes.json"),"w") as f:
    json.dump(raw, f, indent=2); f.write("\n")
print("audit rows events=%d requests=%d" % (len(ea), len(ra)))
