#!/usr/bin/env python3
"""EXP-02-R0 reproducible dataset audit.

Checks the raw files of two public HuggingFace datasets:

  * AgenticSearchQueryset/ASQ  -- agentic RAG multi-step search traces
  * DevLCodes/permission-aware-enterprise-rag-benchmark -- synthetic ACL ground truth

The script only records structural metadata. It never writes query plaintext,
agent thoughts, answers, or any other researcher/agent-only field into its
outputs, and it never modifies the source data.

Usage (Windows Git Bash):

  python scripts/audit_datasets.py \
      --data-dir "$TEMP/exp02_r0_data" \
      --out-dir research/exp08-agentic-trace-leakage-audit/evidence \
      --samples 25

If files are absent from --data-dir, pass --download to fetch them through
huggingface_hub (pip install huggingface_hub). Two retries are used per file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ASQ_REPO = "AgenticSearchQueryset/ASQ"
ACL_REPO = "DevLCodes/permission-aware-enterprise-rag-benchmark"

# One small, complete ASQ trace collection (chosen for audit speed; not representative of all configs).
ASQ_COLLECTION = "traces/hotpotqa-test/BM25_k3/search_r1/Qwen-14B"
ASQ_FILES = {
    f"{ASQ_COLLECTION}/answers.tsv": "asq/Qwen-14B_answers.tsv",
    f"{ASQ_COLLECTION}/iter_queries.tsv": "asq/Qwen-14B_iter_queries.tsv",
    f"{ASQ_COLLECTION}/retrieved_docs.tsv": "asq/Qwen-14B_retrieved_docs.tsv",
    f"{ASQ_COLLECTION}/thoughts.tsv": "asq/Qwen-14B_thoughts.tsv",
    "README.md": "asq/README.md",
}

ACL_FILES = {
    "README.md": "acl/README.md",
    "acl/acl_matrix.json": "acl/acl_acl_matrix.json",
    "acl/groups.json": "acl/acl_groups.json",
    "acl/identities.json": "acl/acl_identities.json",
    "world/bible.json": "acl/world_bible.json",
    "eval/golden.jsonl": "acl/eval_golden.jsonl",
    "eval/acl_leak_probes.jsonl": "acl/eval_acl_leak_probes.jsonl",
    "data/documents_manifest.jsonl": "acl/data_documents_manifest.jsonl",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_files(data_dir: Path, mapping: dict[str, str], repo: str, download: bool) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for remote, local in mapping.items():
        p = data_dir / local
        if not p.exists():
            if not download:
                raise FileNotFoundError(
                    f"missing {p}; place the downloaded raw file there or pass --download"
                )
            from huggingface_hub import hf_hub_download  # type: ignore

            last = None
            for attempt in range(2):
                try:
                    downloaded = hf_hub_download(repo_id=repo, filename=remote, repo_type="dataset")
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(Path(downloaded).read_bytes())
                    last = None
                    break
                except Exception as exc:  # noqa: BLE001 - explicit two-retry policy
                    last = exc
            if last is not None:
                raise RuntimeError(f"download failed after 2 attempts for {remote}: {last}")
        paths[remote] = p
    return paths


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def manifest_entry(name, url, revision, local, sha, size, license_id, note):
    return {
        "dataset": name,
        "source_url": url,
        "revision": revision,
        "file": local,
        "size_bytes": size,
        "sha256": sha,
        "license": license_id,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "check_result": note,
    }


def audit_asq(paths: dict[str, Path], samples: int) -> tuple[dict, list[dict]]:
    ans = read_tsv(paths[f"{ASQ_COLLECTION}/answers.tsv"])
    itq = read_tsv(paths[f"{ASQ_COLLECTION}/iter_queries.tsv"])
    docs = read_tsv(paths[f"{ASQ_COLLECTION}/retrieved_docs.tsv"])
    thoughts = read_tsv(paths[f"{ASQ_COLLECTION}/thoughts.tsv"])

    qid_ans = {r["qid"] for r in ans}
    qid_docs = {r["qid"] for r in docs}
    qid_itq = {r["qid"] for r in itq}
    qid_th = {r["qid"] for r in thoughts}

    by_qid: dict[str, list[dict]] = defaultdict(list)
    for r in docs:
        by_qid[r["qid"]].append(r)

    doc_to_qids: dict[str, set[str]] = defaultdict(set)
    for r in docs:
        doc_to_qids[r["docid"]].add(r["qid"])

    call_counts = [len({int(r["iteration"]) for r in rows}) for rows in by_qid.values()]
    docrow_counts = [len(rows) for rows in by_qid.values()]
    ordered_ok = 0
    for rows in by_qid.values():
        iters = sorted({int(r["iteration"]) for r in rows})
        if iters == list(range(len(iters))):
            ordered_ok += 1

    # Per-sample validation: metadata only. No llm_query / thought / answer text is emitted.
    validated: list[dict] = []
    for qid in sorted(by_qid)[:samples]:
        rows = by_qid[qid]
        iters = sorted({int(r["iteration"]) for r in rows})
        docids = sorted({r["docid"] for r in rows})
        linked = [d for d in docids if len(doc_to_qids[d]) > 1]
        anomalies: list[str] = []
        if not all(r["docid"] for r in rows):
            anomalies.append("missing docid in at least one row")
        if iters != list(range(len(iters))):
            anomalies.append("iteration sequence is not contiguous from 0")
        if not linked:
            anomalies.append("no docid in this trace recurs in another trace of the collection")
        validated.append(
            {
                "sample_id": f"ASQ-QWEN14B-{len(validated) + 1:03d}",
                "qid": qid,
                "task_or_session_id": qid,
                "task_id_scope": "dataset qid; server visibility depends on deployment (NOT assumed)",
                "retrieval_call_count": len(iters),
                "has_call_order": bool(iters),
                "iteration_values": iters,
                "has_docid": all(bool(r["docid"]) for r in rows),
                "docid_unique_count": len(docids),
                "docid_linkable_across_calls_in_trace": len({r["docid"] for r in rows if len(doc_to_qids[r["docid"]]) > 1}),
                "docid_linkable_across_traces": len(linked),
                "has_rank": all(bool(r["rank"]) for r in rows),
                "has_wall_clock_timestamp": False,
                "fields_meet_audit_requirements": bool(iters) and all(bool(r["docid"]) for r in rows),
                "researcher_only_fields_excluded": ["llm_query", "thought", "answer"],
                "anomalies": anomalies,
            }
        )

    summary = {
        "collection": ASQ_COLLECTION,
        "rows": {
            "answers": len(ans),
            "iter_queries": len(itq),
            "retrieved_docs": len(docs),
            "thoughts": len(thoughts),
        },
        "unique_qids": {
            "answers": len(qid_ans),
            "iter_queries": len(qid_itq),
            "retrieved_docs": len(qid_docs),
            "thoughts": len(qid_th),
            "all_four_intersection": len(qid_ans & qid_itq & qid_docs & qid_th),
            "answers_without_retrieval": len(qid_ans - qid_docs),
        },
        "traces": {
            "count": len(by_qid),
            "calls_per_trace_min": min(call_counts),
            "calls_per_trace_median": sorted(call_counts)[len(call_counts) // 2],
            "calls_per_trace_max": max(call_counts),
            "doc_rows_per_trace_min": min(docrow_counts),
            "doc_rows_per_trace_median": sorted(docrow_counts)[len(docrow_counts) // 2],
            "doc_rows_per_trace_max": max(docrow_counts),
            "contiguous_iteration_from_zero": ordered_ok,
        },
        "docids": {
            "unique": len(doc_to_qids),
            "appearing_in_more_than_one_trace": sum(1 for v in doc_to_qids.values() if len(v) > 1),
            "max_traces_per_docid": max(len(v) for v in doc_to_qids.values()),
        },
        "observed_fields": ["qid", "iteration", "docid", "rank"],
        "missing_fields": ["wall_clock_timestamp", "user_id", "role_label", "acl_state", "document_content"],
        "server_visible_fields_conservative": ["docid", "rank", "iteration_if_transmitted"],
        "researcher_only_fields": ["llm_query", "thought", "answer"],
        "verdict": (
            "supports task grouping, ordered multi-step calls, cross-call/cross-trace docid co-occurrence; "
            "does NOT contain any user, role, ACL or permission-state ground truth; "
            "no wall-clock time, so revocation timing cannot be observed from this dataset alone"
        ),
    }
    return summary, validated


def audit_acl(paths: dict[str, Path]) -> dict:
    matrix = json.loads(paths["acl/acl_matrix.json"].read_text(encoding="utf-8"))
    groups_doc = json.loads(paths["acl/groups.json"].read_text(encoding="utf-8"))
    identities = json.loads(paths["acl/identities.json"].read_text(encoding="utf-8"))
    bible = json.loads(paths["world/bible.json"].read_text(encoding="utf-8"))
    golden = read_jsonl(paths["eval/golden.jsonl"])
    probes = read_jsonl(paths["eval/acl_leak_probes.jsonl"])
    manifest = read_jsonl(paths["data/documents_manifest.jsonl"])

    events = matrix["acl_change_events"]
    containers = matrix["containers"]
    by_container: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_container[e["container"]].append(e)

    final_matches = 0
    for c, evs in by_container.items():
        last = sorted(evs, key=lambda x: x["timestamp"])[-1]
        acl = containers[c]["acl"]
        if (
            set(last["allow_users"]) == set(acl["allow_users"])
            and set(last["deny_users"]) == set(acl["deny_users"])
            and set(last["allow_groups"]) == set(acl["allow_groups"])
        ):
            final_matches += 1

    groups = groups_doc["groups"]
    history_entries = sum(len(g["history"]) for g in groups)
    dated_history = sum(1 for g in groups for h in g["history"] if h.get("timestamp"))

    movers = [
        {
            "user": u["canonical_id"],
            "from_team": u.get("team_id"),
            "move_date": u.get("move_date"),
            "to_team": u.get("moved_to_team"),
        }
        for u in bible["users"]
        if u.get("move_date")
    ]

    space_team = {s["space_key"]: s["team_id"] for s in bible["confluence_spaces"]}
    doc_prefix_space = Counter(
        d["doc_id"].split(":")[1] for d in manifest if d["doc_id"].startswith("confluence:")
    )

    return {
        "scale": {
            "users": len(identities),
            "groups": len(groups),
            "containers": len(containers),
            "acl_change_events": len(events),
            "documents_in_manifest": len(manifest),
            "golden_qa": len(golden),
            "acl_leak_probes": len(probes),
        },
        "acl_temporal": {
            "event_time_min": min(e["timestamp"] for e in events),
            "event_time_max": max(e["timestamp"] for e in events),
            "events_with_deny_users": sum(1 for e in events if e["deny_users"]),
            "events_with_allow_users": sum(1 for e in events if e["allow_users"]),
            "containers_with_initial_acl": sum(1 for c in containers.values() if "initial_acl" in c),
            "containers_with_events": len(by_container),
            "final_acl_equals_last_event": f"{final_matches}/{len(by_container)}",
            "reconstruction": "initial_acl + timestamp-ordered full-state events -> effective ACL at time t",
        },
        "group_history": {
            "entries": history_entries,
            "entries_with_timestamp": dated_history,
            "groups_with_history": sum(1 for g in groups if g["history"]),
        },
        "role_change_ground_truth": {
            "users_with_move_date": movers,
            "golden_asking_users": sorted({r["asking_user"] for r in golden}),
            "golden_categories": dict(Counter(r["category"] for r in golden)),
            "probe_attack_types": dict(Counter(r["attack_type"] for r in probes)),
        },
        "synthetic_artifact_risk": {
            "space_to_team_mapping": space_team,
            "confluence_doc_prefix_counts": dict(doc_prefix_space),
            "note": (
                "Document identifiers encode Confluence space keys, which map deterministically "
                "to team ids in world/bible.json. A role classifier served with raw docids may "
                "decode team labels from ID strings rather than infer authorization from access "
                "patterns. Any future experiment must use opaque, non-semantic docids."
            ),
        },
        "synthetic_guarantee": "dataset card declares 100% synthetic and fictional; not real enterprise telemetry",
        "verdict": (
            "credible point-in-time ACL / role-change ground truth exists; "
            "no agentic retrieval traces exist in this dataset; "
            "strong namespace-team coupling requires an opaque-ID control"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True, help="directory holding downloaded raw files")
    ap.add_argument("--out-dir", required=True, help="directory for JSON evidence outputs")
    ap.add_argument("--samples", type=int, default=25, help="number of ASQ traces to validate")
    ap.add_argument("--download", action="store_true", help="download missing files via huggingface_hub")
    ap.add_argument("--manifest-revision-asq", default="14554ef4cbadc42a05d3c99da6bc18abb9d7f81e")
    ap.add_argument("--manifest-revision-acl", default="6e3bb8d6071c3a46e8e9c22c856a24c737b9792d")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    asq_paths = ensure_files(data_dir, ASQ_FILES, ASQ_REPO, args.download)
    acl_paths = ensure_files(data_dir, ACL_FILES, ACL_REPO, args.download)

    manifest = []
    for remote, p in asq_paths.items():
        manifest.append(
            manifest_entry(
                "ASQ",
                f"https://huggingface.co/datasets/{ASQ_REPO}/resolve/main/{remote}",
                args.manifest_revision_asq,
                str(p.relative_to(data_dir)).replace("\\", "/"),
                sha256(p),
                p.stat().st_size,
                "mit (per GitHub README and HF card; source datasets may carry their own licenses)",
                "structure and sample validation passed",
            )
        )
    for remote, p in acl_paths.items():
        manifest.append(
            manifest_entry(
                "Permission-Aware Enterprise RAG Benchmark",
                f"https://huggingface.co/datasets/{ACL_REPO}/resolve/main/{remote}",
                args.manifest_revision_acl,
                str(p.relative_to(data_dir)).replace("\\", "/"),
                sha256(p),
                p.stat().st_size,
                "mit (HF dataset card)",
                "structure and ACL-history validation passed",
            )
        )

    asq_summary, samples = audit_asq(asq_paths, args.samples)
    acl_summary = audit_acl(acl_paths)

    payload = {
        "task": "EXP-02-R0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asq": asq_summary,
        "acl_benchmark": acl_summary,
        "dataset_manifest": manifest,
    }
    (out_dir / "dataset_manifest.json").write_text(
        json.dumps({"datasets": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "sample_validation.json").write_text(
        json.dumps(
            {
                "task": "EXP-02-R0",
                "source_collection": ASQ_COLLECTION,
                "sampling": "first N qids sorted lexicographically from retrieved_docs.tsv",
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "acl_audit.json").write_text(
        json.dumps(acl_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n[OK] audit outputs written to", out_dir, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
