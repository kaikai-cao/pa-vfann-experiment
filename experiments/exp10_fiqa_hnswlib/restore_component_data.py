#!/usr/bin/env python3
"""EXP-10B.1 data gate: restore revision-pinned BEIR first-party FiQA components.

This script never uses main-branch files, Parquet, third-party mirrors, or
reconstructed split logic. The official ZIP MD5 remains NOT_VERIFIED.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "experiment_config.json"
RAW_DIR = ROOT / "data" / "exp10_component_sources"
EXTRACTED_DIR = ROOT / "data" / "exp10_fiqa_extracted"
MANIFEST_PATH = ROOT / "data" / "exp10_fiqa_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_id_hash(ids: set[str]) -> str:
    payload = "\n".join(sorted(ids))
    if ids:
        payload += "\n"
    return sha256_text(payload)


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_component(spec: dict[str, Any], key: str) -> Path:
    local_dir = RAW_DIR / key
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"[download] {key}: {spec['repo_id']}@{spec['revision']}/{spec['filename']}", flush=True)
    return Path(
        hf_hub_download(
            repo_id=spec["repo_id"],
            filename=spec["filename"],
            revision=spec["revision"],
            repo_type="dataset",
            local_dir=str(local_dir),
        )
    )


def check_hashes(key: str, spec: dict[str, Any], path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    digest = sha256_file(path)
    expected_size = spec.get("expected_size_bytes")
    expected_sha = spec.get("expected_sha256")
    if expected_size is not None and size != expected_size:
        raise RuntimeError(f"{key}: size mismatch: expected {expected_size}, got {size}")
    if expected_sha is not None and digest != expected_sha:
        raise RuntimeError(f"{key}: SHA-256 mismatch: expected {expected_sha}, got {digest}")
    if digest.startswith("version https://git-lfs.github.com/spec/"):
        raise RuntimeError(f"{key}: downloaded LFS pointer instead of file bytes")
    return {
        "repo_id": spec["repo_id"],
        "revision": spec["revision"],
        "filename": spec["filename"],
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "size_bytes": size,
        "sha256": digest,
        "expected_size_bytes": expected_size,
        "expected_sha256": expected_sha,
    }


def decompress_gz(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(source, "rb") as src, target.open("wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
    return target


def parse_jsonl(path: Path, id_field: str, required_fields: set[str]) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                raise RuntimeError(f"{path.name}: blank line at {line_no}")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path.name}: invalid JSON at line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"{path.name}: line {line_no} is not an object")
            missing = required_fields - set(row)
            if missing:
                raise RuntimeError(f"{path.name}: line {line_no} missing fields {sorted(missing)}")
            doc_id = row[id_field]
            if not isinstance(doc_id, str) or not doc_id:
                raise RuntimeError(f"{path.name}: line {line_no} invalid {id_field}")
            if doc_id in ids:
                raise RuntimeError(f"{path.name}: duplicate {id_field} at line {line_no}: {doc_id}")
            ids.add(doc_id)
            rows.append(row)
    return rows, ids


def parse_qrels(path: Path) -> tuple[list[tuple[str, str, float]], set[str], set[str]]:
    rows: list[tuple[str, str, float]] = []
    query_ids: set[str] = set()
    corpus_ids: set[str] = set()
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise RuntimeError("qrels: empty file") from exc
        if header != ["query-id", "corpus-id", "score"]:
            raise RuntimeError(f"qrels: unexpected header {header!r}")
        for row_no, row in enumerate(reader, 2):
            if len(row) != 3:
                raise RuntimeError(f"qrels: invalid row {row_no}: {row!r}")
            qid, cid, score_text = row
            if not qid or not cid:
                raise RuntimeError(f"qrels: empty ID at row {row_no}")
            pair = (qid, cid)
            if pair in seen:
                raise RuntimeError(f"qrels: duplicate query-document pair at row {row_no}: {pair}")
            seen.add(pair)
            try:
                score = float(score_text)
            except ValueError as exc:
                raise RuntimeError(f"qrels: invalid score at row {row_no}: {score_text!r}") from exc
            rows.append((qid, cid, score))
            query_ids.add(qid)
            corpus_ids.add(cid)
    return rows, query_ids, corpus_ids


def hf_license(repo_id: str, revision: str) -> str:
    try:
        info = HfApi().dataset_info(repo_id=repo_id, revision=revision)
        card = info.card_data
        if card is None:
            return "NOT_DECLARED_IN_DATASET_CARD"
        license_value = getattr(card, "license", None)
        return str(license_value) if license_value is not None else "NOT_DECLARED_IN_DATASET_CARD"
    except Exception as exc:  # pragma: no cover - network diagnostic only
        return f"UNVERIFIED:{type(exc).__name__}"


def build_manifest(cfg: dict[str, Any]) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    components: dict[str, Any] = {}
    for key in ("corpus", "queries", "qrels"):
        spec = cfg["data_sources"][key]
        raw_path = fetch_component(spec, key)
        components[key] = check_hashes(key, spec, raw_path)

    corpus_jsonl = decompress_gz(
        ROOT / components["corpus"]["path"],
        EXTRACTED_DIR / "corpus.jsonl",
    )
    queries_jsonl = decompress_gz(
        ROOT / components["queries"]["path"],
        EXTRACTED_DIR / "queries.jsonl",
    )

    corpus_rows, corpus_ids = parse_jsonl(corpus_jsonl, "_id", {"_id", "title", "text"})
    query_rows, query_ids_all = parse_jsonl(queries_jsonl, "_id", {"_id", "text"})

    qrels_path = ROOT / components["qrels"]["path"]
    qrels_rows, qrels_query_ids, qrels_corpus_ids = parse_qrels(qrels_path)

    expected = cfg["expected_counts"]
    if len(corpus_rows) != expected["corpus"]:
        raise RuntimeError(f"corpus count mismatch: expected {expected['corpus']}, got {len(corpus_rows)}")
    if len(query_rows) != expected["queries_all_splits"]:
        raise RuntimeError(
            f"all-split query count mismatch: expected {expected['queries_all_splits']}, got {len(query_rows)}"
        )

    missing_corpus = qrels_corpus_ids - corpus_ids
    if missing_corpus:
        sample = sorted(missing_corpus)[:10]
        raise RuntimeError(f"qrels corpus IDs missing from corpus: {len(missing_corpus)}; sample={sample}")

    test_query_ids = qrels_query_ids & query_ids_all
    missing_queries = qrels_query_ids - query_ids_all
    if missing_queries:
        sample = sorted(missing_queries)[:10]
        raise RuntimeError(f"qrels query IDs missing from queries: {len(missing_queries)}; sample={sample}")
    if test_query_ids != qrels_query_ids:
        raise RuntimeError("test query set differs from qrels query set")
    if len(test_query_ids) != expected["queries_test"]:
        raise RuntimeError(f"test query count mismatch: expected {expected['queries_test']}, got {len(test_query_ids)}")
    if len(qrels_rows) != expected["qrels_pairs"]:
        raise RuntimeError(f"qrels pair count mismatch: expected {expected['qrels_pairs']}, got {len(qrels_rows)}")
    for qid in qrels_query_ids:
        if not any(row[0] == qid for row in qrels_rows):
            raise RuntimeError(f"test query without qrels: {qid}")

    manifest = {
        "experiment": cfg["experiment"],
        "data_gate": "PASS_COMPONENT_ARTIFACTS",
        "data_source_description": cfg["amendment"],
        "original_zip_md5": {
            **cfg["original_zip_md5"],
            "note": "Original BEIR UKP ZIP was not downloaded; MD5 was not verified in EXP-10B.1.",
        },
        "components": components,
        "extracted": {
            "corpus_jsonl": {
                "path": str(corpus_jsonl.relative_to(ROOT)).replace("\\", "/"),
                "size_bytes": corpus_jsonl.stat().st_size,
                "sha256": sha256_file(corpus_jsonl),
                "rows": len(corpus_rows),
            },
            "queries_jsonl": {
                "path": str(queries_jsonl.relative_to(ROOT)).replace("\\", "/"),
                "size_bytes": queries_jsonl.stat().st_size,
                "sha256": sha256_file(queries_jsonl),
                "rows": len(query_rows),
            },
        },
        "counts": {
            "corpus": len(corpus_rows),
            "queries_all_splits": len(query_rows),
            "queries_test": len(test_query_ids),
            "qrels_pairs": len(qrels_rows),
        },
        "id_set_hashes": {
            "corpus_ids_sha256": canonical_id_hash(corpus_ids),
            "queries_all_ids_sha256": canonical_id_hash(query_ids_all),
            "test_query_ids_sha256": canonical_id_hash(test_query_ids),
            "qrels_query_ids_sha256": canonical_id_hash(qrels_query_ids),
            "qrels_corpus_ids_sha256": canonical_id_hash(qrels_corpus_ids),
        },
        "structure_checks": {
            "corpus_ids_unique": True,
            "query_ids_unique": True,
            "qrels_header_valid": True,
            "qrels_pairs_unique": True,
            "qrels_query_ids_resolve": True,
            "qrels_corpus_ids_resolve": True,
            "test_query_set_equals_qrels_query_set": True,
            "every_test_query_has_qrels": True,
            "test_split_rule": "test query IDs selected from full 6648 queries by qrels query IDs",
        },
        "license": {
            "corpus": hf_license(components["corpus"]["repo_id"], components["corpus"]["revision"]),
            "queries": hf_license(components["queries"]["repo_id"], components["queries"]["revision"]),
            "qrels": hf_license(components["qrels"]["repo_id"], components["qrels"]["revision"]),
            "source": "Hugging Face dataset cards at pinned revisions",
        },
        "test_query_ids_sample": sorted(test_query_ids)[:20],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-manifest", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    manifest = build_manifest(cfg)
    print(f"[data-gate] {manifest['data_gate']}")
    print(f"[manifest] {MANIFEST_PATH.relative_to(ROOT)}")
    if args.print_manifest:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[data-gate] STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
