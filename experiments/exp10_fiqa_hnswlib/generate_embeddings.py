#!/usr/bin/env python3
"""EXP-10B.1: generate revision-pinned all-MiniLM-L6-v2 FiQA embeddings (CPU)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# CPU embedding is a separate preprocessing stage from the single-thread HNSW
# query path. Eight threads are fixed here for tractable runtime; the value is
# recorded in the manifest.
EMB_THREADS = 8
for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, str(EMB_THREADS))

import numpy as np
import torch
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer

torch.set_num_threads(EMB_THREADS)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "experiment_config.json"
MANIFEST_PATH = ROOT / "data" / "exp10_fiqa_manifest.json"
OUT_DIR = ROOT / "data" / "exp10_fiqa_embeddings"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_ids(path: Path, ids: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for value in ids:
            f.write(value + "\n")


def main() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    model_cfg = cfg["model"]
    model_id = model_cfg["name"]
    revision = model_cfg["revision"]
    dim = int(model_cfg["dim"])

    info = HfApi().model_info(repo_id=model_id, revision=revision)
    if info.sha != revision:
        raise RuntimeError(f"model revision mismatch: requested {revision}, resolved {info.sha}")
    card = getattr(info, "card_data", None)
    if isinstance(card, dict):
        model_license = str(card.get("license", "NOT_DECLARED_IN_MODEL_CARD"))
    elif card is not None and getattr(card, "license", None):
        model_license = str(card.license)
    else:
        model_license = "NOT_DECLARED_IN_MODEL_CARD"

    corpus_rows = read_jsonl(ROOT / data_manifest["extracted"]["corpus_jsonl"]["path"])
    all_query_rows = read_jsonl(ROOT / data_manifest["extracted"]["queries_jsonl"]["path"])
    qrels_path = ROOT / data_manifest["components"]["qrels"]["path"]
    with qrels_path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        if header != ["query-id", "corpus-id", "score"]:
            raise RuntimeError(f"qrels header mismatch: {header}")
        test_ids = sorted({row[0] for row in reader if len(row) == 3})

    if len(corpus_rows) != 57638 or len(all_query_rows) != 6648 or len(test_ids) != 648:
        raise RuntimeError("unexpected data counts before embedding")
    query_by_id = {row["_id"]: row for row in all_query_rows}
    missing = [qid for qid in test_ids if qid not in query_by_id]
    if missing:
        raise RuntimeError(f"test query IDs missing: {len(missing)}")

    print(f"[model] {model_id}@{revision}", flush=True)
    model = SentenceTransformer(
        model_id,
        revision=revision,
        device="cpu",
        trust_remote_code=False,
    )
    print(f"[model] loaded dim={model.get_sentence_embedding_dimension()}", flush=True)

    def encode(texts: list[str], label: str) -> np.ndarray:
        emb = model.encode(
            texts,
            batch_size=256,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
            device="cpu",
        )
        emb = np.ascontiguousarray(emb, dtype=np.float32)
        if emb.ndim != 2 or emb.shape[1] != dim:
            raise RuntimeError(f"{label}: unexpected shape {emb.shape}, expected (*, {dim})")
        norms = np.linalg.norm(emb.astype(np.float64), axis=1)
        max_dev = float(np.max(np.abs(norms - 1.0)))
        if max_dev > 1e-4:
            raise RuntimeError(f"{label}: max norm deviation too large: {max_dev}")
        print(f"[encode] {label}: shape={emb.shape} max_norm_dev={max_dev:.3e}", flush=True)
        return emb

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus_ids = [str(row["_id"]) for row in corpus_rows]
    corpus_texts = [f"{row['title']}\n{row['text']}" for row in corpus_rows]
    test_texts = [str(query_by_id[qid]["text"]) for qid in test_ids]

    # BEIR's all-MiniLM-L6-v2 usage encodes query text alone and document
    # title+text; this convention is fixed here before any measurement.
    corpus_emb = encode(corpus_texts, "corpus")
    query_emb = encode(test_texts, "test_queries")

    corpus_bin = OUT_DIR / "corpus.f32"
    query_bin = OUT_DIR / "test_queries.f32"
    corpus_ids_path = OUT_DIR / "corpus_ids.txt"
    query_ids_path = OUT_DIR / "test_query_ids.txt"
    corpus_emb.tofile(corpus_bin)
    query_emb.tofile(query_bin)
    write_ids(corpus_ids_path, corpus_ids)
    write_ids(query_ids_path, test_ids)

    manifest = {
        "experiment": cfg["experiment"],
        "model": {
            "id": model_id,
            "requested_revision": revision,
            "resolved_revision": info.sha,
            "license": model_license,
            "device": "cpu",
            "cpu_threads": EMB_THREADS,
            "dtype": "float32",
            "dim": dim,
            "normalize_embeddings": True,
            "batch_size": 256,
            "sentence_convention": {
                "corpus": "title + newline + text",
                "query": "query text only",
            },
            "test_query_order": "lexicographically sorted qrels query IDs",
        },
        "counts": {
            "corpus": len(corpus_ids),
            "test_queries": len(test_ids),
        },
        "files": {
            name: {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for name, path in (
                ("corpus_embeddings", corpus_bin),
                ("test_query_embeddings", query_bin),
                ("corpus_ids", corpus_ids_path),
                ("test_query_ids", query_ids_path),
            )
        },
        "norm_check": {
            "corpus_max_abs_deviation": float(
                np.max(np.abs(np.linalg.norm(corpus_emb.astype(np.float64), axis=1) - 1.0))
            ),
            "queries_max_abs_deviation": float(
                np.max(np.abs(np.linalg.norm(query_emb.astype(np.float64), axis=1) - 1.0))
            ),
        },
        "data_gate": data_manifest["data_gate"],
        "original_zip_md5_status": data_manifest["original_zip_md5"]["status"],
    }
    manifest_path = OUT_DIR / "embedding_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[embedding-manifest] {manifest_path.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[embedding] STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
