"""EXP-10A Phase 0 validator.

Consumes the raw JSONL emitted by the C++ probe and verifies V1-V5.
Writes:
  results/raw/exp10a_trace_summary.csv
  results/raw/exp10a_first_touch.jsonl
  results/raw/exp10a_sample_query0.json
  results/raw/exp10a_validation.json

Observation scope: HNSW query distance-evaluation trace (algorithm level).
No hardware cache / prefetch / physical-memory claim is made.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
PATCH = ROOT / "patches" / "hnswlib-v0.9.0-query-trace.patch"

ALLOWED_SITES = {
    "entrypoint",
    "upper_layer_neighbor",
    "level0_entrypoint",
    "level0_neighbor",
}
LABEL_BASE = 100000
LABEL_STEP = 17
N_EXPECTED = 1000
NQ_EXPECTED = 50
K_EXPECTED = 10


def load_jsonl(name: str) -> list[dict]:
    path = RAW / name
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def group_by_query(rows: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        out[int(r["query_id"])].append(r)
    return out


def main() -> int:
    trace = load_jsonl("exp10a_synthetic_trace.jsonl")
    summary_rows = load_jsonl("exp10a_probe_summary.jsonl")
    up_topk = load_jsonl("exp10a_upstream_topk.jsonl")
    ins_topk = load_jsonl("exp10a_instrumented_topk.jsonl")
    off_topk = load_jsonl("exp10a_sinkoff_topk.jsonl")

    primary = [r for r in summary_rows if r.get("record") == "primary"]
    rebuilt = [r for r in summary_rows if r.get("record") == "rebuilt"]
    trace_by_q = group_by_query(trace)

    # ---------------- V1: complete event coverage ----------------
    v1_errors: list[str] = []
    v1_stats = {
        "queries_checked": len(primary),
        "total_events": len(trace),
        "label_mapping_errors": 0,
        "event_index_errors": 0,
        "queries_with_level0": 0,
        "queries_with_upper": 0,
        "max_counter_minus_event": 0,
    }
    if len(primary) != NQ_EXPECTED:
        v1_errors.append(f"expected {NQ_EXPECTED} primary queries, got {len(primary)}")
    expected_labels = {LABEL_BASE + LABEL_STEP * i for i in range(N_EXPECTED)}
    for s in primary:
        q = int(s["query_id"])
        ev = trace_by_q.get(q, [])
        if not ev:
            v1_errors.append(f"q={q}: empty event stream")
            continue
        if int(s["event_count"]) != len(ev):
            v1_errors.append(f"q={q}: summary event_count != trace rows")
        if int(s["event_count"]) != int(s["distance_call_count"]):
            v1_errors.append(
                f"q={q}: event_count {s['event_count']} != distance_call_count {s['distance_call_count']}"
            )
        v1_stats["max_counter_minus_event"] = max(
            v1_stats["max_counter_minus_event"],
            int(s["distance_call_count"]) - int(s["event_count"]),
        )
        if s["has_level0"]:
            v1_stats["queries_with_level0"] += 1
        if s["has_upper"]:
            v1_stats["queries_with_upper"] += 1
        if int(s["sinkoff_event_count"]) != 0:
            v1_errors.append(f"q={q}: sink-off run emitted events")
        for i, e in enumerate(ev):
            if int(e["event_index"]) != i:
                v1_stats["event_index_errors"] += 1
            ext = int(e["external_id"])
            if ext not in expected_labels:
                v1_stats["label_mapping_errors"] += 1
            if ext != LABEL_BASE + LABEL_STEP * int(e["internal_id"]):
                v1_stats["label_mapping_errors"] += 1
            if e["event_site"] not in ALLOWED_SITES:
                v1_errors.append(f"q={q}: unexpected event_site {e['event_site']}")
    if v1_stats["label_mapping_errors"]:
        v1_errors.append(f"external-id mapping errors: {v1_stats['label_mapping_errors']}")
    if v1_stats["event_index_errors"]:
        v1_errors.append(f"event_index non-contiguous count: {v1_stats['event_index_errors']}")
    if v1_stats["queries_with_level0"] != NQ_EXPECTED:
        v1_errors.append("not all queries have level-0 events")
    if v1_stats["queries_with_upper"] < 1:
        v1_errors.append("no level>0 event collected")
    site_counts = Counter(e["event_site"] for e in trace)
    if site_counts["upper_layer_neighbor"] == 0:
        v1_errors.append("no upper_layer_neighbor events")
    v1_stats["site_counts"] = dict(site_counts)
    v1 = {"pass": not v1_errors, "errors": v1_errors, "stats": v1_stats}

    # ---------------- V2: search result invariance ----------------
    def topk_key(rows: list[dict]) -> list[tuple]:
        return [
            (int(r["query_id"]), int(r["rank"]), int(r["external_id"]), r["dist_bits"])
            for r in rows
        ]

    up_k, ins_k, off_k = topk_key(up_topk), topk_key(ins_topk), topk_key(off_topk)
    v2_mismatch = {
        "upstream_vs_instrumented": sum(1 for a, b in zip(up_k, ins_k) if a != b)
        + abs(len(up_k) - len(ins_k)),
        "instrumented_vs_sinkoff": sum(1 for a, b in zip(ins_k, off_k) if a != b)
        + abs(len(ins_k) - len(off_k)),
    }
    v2_errors = []
    if len(up_k) != NQ_EXPECTED * K_EXPECTED:
        v2_errors.append(f"upstream top-k rows {len(up_k)}")
    for label, n in v2_mismatch.items():
        if n:
            v2_errors.append(f"{label}: {n} row mismatches")
    v2 = {
        "pass": not v2_errors,
        "errors": v2_errors,
        "rows_compared": len(up_k),
        "mismatches": v2_mismatch,
        "comparison": "exact (query_id, rank, external_id, float32 bit pattern)",
    }

    # ---------------- V3: trace reproducibility + first-touch derivation ----------------
    rebuilt_by_q = {int(r["query_id"]): r["rebuilt_trace_hash"] for r in rebuilt}
    v3_errors: list[str] = []
    v3_counts = {"repeat_hash_match": 0, "rebuilt_hash_match": 0}
    if len(rebuilt) != NQ_EXPECTED:
        v3_errors.append(f"rebuilt records {len(rebuilt)}")
    for s in primary:
        q = int(s["query_id"])
        if s["trace_hash"] != s["repeat_trace_hash"]:
            v3_errors.append(f"q={q}: repeat trace hash differs")
        else:
            v3_counts["repeat_hash_match"] += 1
        if q not in rebuilt_by_q:
            v3_errors.append(f"q={q}: missing rebuilt hash")
        elif s["trace_hash"] != rebuilt_by_q[q]:
            v3_errors.append(f"q={q}: rebuilt trace hash differs")
        else:
            v3_counts["rebuilt_hash_match"] += 1

    # Derived view B: unique first-touch trace, in complete-stream order.
    first_touch_path = RAW / "exp10a_first_touch.jsonl"
    ft_rows: list[dict] = []
    with first_touch_path.open("w", encoding="utf-8", newline="\n") as fh:
        for q in sorted(trace_by_q):
            seen: set[int] = set()
            ft_index = 0
            for e in trace_by_q[q]:
                ext = int(e["external_id"])
                if ext in seen:
                    continue
                seen.add(ext)
                row = {
                    "query_id": q,
                    "first_touch_index": ft_index,
                    "event_index": int(e["event_index"]),
                    "external_id": ext,
                    "level": int(e["level"]),
                    "event_site": e["event_site"],
                }
                ft_rows.append(row)
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                ft_index += 1
    # Recompute derivation independently and check it matches the written view.
    ft_by_q: dict[int, list[dict]] = defaultdict(list)
    for r in ft_rows:
        ft_by_q[r["query_id"]].append(r)
    derivation_ok = True
    for q in sorted(trace_by_q):
        derived = []
        seen = set()
        for e in trace_by_q[q]:
            ext = int(e["external_id"])
            if ext not in seen:
                seen.add(ext)
                derived.append((int(e["event_index"]), ext))
        written = [(r["event_index"], r["external_id"]) for r in ft_by_q[q]]
        if derived != written:
            derivation_ok = False
            v3_errors.append(f"q={q}: first-touch derivation not reproducible")
    v3_counts["first_touch_total"] = len(ft_rows)
    v3_counts["derivation_ok"] = derivation_ok
    v3 = {"pass": not v3_errors, "errors": v3_errors, "stats": v3_counts}

    # ---------------- V4:层级 / 重复访问样例 ----------------
    sample_q = 0
    ev0 = trace_by_q.get(sample_q, [])
    seen0: set[int] = set()
    ft0 = []
    repeated = []
    for e in ev0:
        ext = int(e["external_id"])
        if ext in seen0:
            repeated.append(
                {
                    "event_index": int(e["event_index"]),
                    "external_id": ext,
                    "level": int(e["level"]),
                    "event_site": e["event_site"],
                }
            )
        else:
            seen0.add(ext)
            ft0.append(
                {
                    "first_touch_index": len(ft0),
                    "event_index": int(e["event_index"]),
                    "external_id": ext,
                    "level": int(e["level"]),
                    "event_site": e["event_site"],
                }
            )
    sample = {
        "query_id": sample_q,
        "complete_event_count": len(ev0),
        "unique_documents": len(ft0),
        "repeated_distance_events": len(repeated),
        "site_counts": dict(Counter(e["event_site"] for e in ev0)),
        "first_25_complete_events": ev0[:25],
        "first_25_first_touch": ft0[:25],
        "first_10_repeats": repeated[:10],
        "note": (
            "Complete stream preserves every distance-function call (duplicates allowed); "
            "unique first-touch keeps the first occurrence of each external_id in stream order."
        ),
    }
    sample_path = RAW / "exp10a_sample_query0.json"
    sample_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    v4_errors = []
    if not ev0:
        v4_errors.append("sample query has no events")
    if len(ft0) >= len(ev0):
        v4_errors.append("sample shows no repeated distance evaluation")
    if not any(e["level"] > 0 for e in ev0):
        v4_errors.append("sample has no upper-layer event")
    if not any(e["level"] == 0 for e in ev0):
        v4_errors.append("sample has no level-0 event")
    v4 = {
        "pass": not v4_errors,
        "errors": v4_errors,
        "sample_query": sample_q,
        "complete_count": len(ev0),
        "unique_first_touch_count": len(ft0),
        "repeated_count": len(repeated),
    }

    # ---------------- V5: static instrumentation-scope audit ----------------
    patch_text = PATCH.read_text(encoding="utf-8", errors="replace")
    added = [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    # Every added line must be an allowed observation-only construct.
    allowed_patterns = [
        re.compile(r"^\s*$"),
        re.compile(r"^\s*//"),
        re.compile(r"^\s*#\s*(pragma|ifdef|else|endif|include|define)"),
        re.compile(r"^\s*(extern\s|template\s|static\s|inline\s|bool\s|uint64_t\s|void\s+\*)"),
        re.compile(r"^\s*struct\s+HnswTraceDistState"),
        re.compile(r"HnswTraceDistState<"),
        re.compile(r"hnswlib::DISTFUNC<T>"),
        re.compile(r"fstdistfunc_\s*=\s*&hnsw_trace_counting_distfunc"),
        re.compile(r"HNSW_TRACE_SITE\(|hnsw_trace_emit\(|g_hnsw_trace_sink_enabled"),
        re.compile(r"getExternalLabel\(|\(int\)\(lvl\)|do\s*\{|\+\+|\}|\);?"),
        re.compile(r"^\s*(int level,|const char \*event_site\);)"),
    ]
    disallowed = [
        line for line in added if not any(p.search(line) for p in allowed_patterns)
    ]
    forbidden_tokens = [
        "getNeighborsByHeuristic2",
        "mutuallyConnectNewElement",
        "addPoint",
        "should_stop_search",
        "should_consider_candidate",
        "visited_array[",
        "lowerBound =",
        "candidate_set.emplace",
        "top_candidates.emplace",
    ]
    forbidden_hits = [t for t in forbidden_tokens if any(t in line for line in added)]
    v5_errors = []
    if disallowed:
        v5_errors.append(f"{len(disallowed)} added lines outside allowlist: {disallowed[:3]}")
    if forbidden_hits:
        v5_errors.append(f"forbidden control-flow tokens in added lines: {forbidden_hits}")
    if site_counts and set(site_counts) - ALLOWED_SITES:
        v5_errors.append("unexpected event_site in data")
    if any(int(s["sinkoff_event_count"]) != 0 for s in primary):
        v5_errors.append("trace sink emitted events while disabled")
    v5 = {
        "pass": not v5_errors,
        "errors": v5_errors,
        "added_lines": len(added),
        "disallowed_added_lines": disallowed,
        "forbidden_tokens": forbidden_hits,
        "note": (
            "Static audit covers the patch diff only. Scope is single-thread searchKnn; "
            "no claim about concurrent trace safety. Build/addPoint path untouched."
        ),
    }

    # ---------------- per-query summary CSV ----------------
    rebuilt_lookup = {int(r["query_id"]): r["rebuilt_trace_hash"] for r in rebuilt}
    csv_path = RAW / "exp10a_trace_summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "query_id",
                "event_count",
                "distance_call_count",
                "unique_documents",
                "has_level0",
                "has_upper",
                "sinkoff_event_count",
                "trace_hash",
                "repeat_trace_hash",
                "rebuilt_trace_hash",
                "hash_match",
            ]
        )
        for s in primary:
            q = int(s["query_id"])
            writer.writerow(
                [
                    q,
                    s["event_count"],
                    s["distance_call_count"],
                    len(ft_by_q[q]),
                    s["has_level0"],
                    s["has_upper"],
                    s["sinkoff_event_count"],
                    s["trace_hash"],
                    s["repeat_trace_hash"],
                    rebuilt_lookup.get(q, ""),
                    s["trace_hash"] == s["repeat_trace_hash"]
                    and s["trace_hash"] == rebuilt_lookup.get(q),
                ]
            )

    verdict = all([v1["pass"], v2["pass"], v3["pass"], v4["pass"], v5["pass"]])
    validation = {
        "phase": "EXP-10A Phase 0",
        "verdict": "PASS" if verdict else "STOP",
        "V1": v1,
        "V2": v2,
        "V3": v3,
        "V4": v4,
        "V5": v5,
        "observation_scope": "HNSW query distance-evaluation trace (algorithm level only)",
    }
    (RAW / "exp10a_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"verdict={validation['verdict']}")
    for k in ("V1", "V2", "V3", "V4", "V5"):
        print(f"{k}: pass={validation[k]['pass']} errors={validation[k]['errors'][:3]}")
    print(f"site_counts={site_counts}")
    print(f"sample q0: {v4['complete_count']} events / {v4['unique_first_touch_count']} unique / {v4['repeated_count']} repeats")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
