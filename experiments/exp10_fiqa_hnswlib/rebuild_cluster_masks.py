#!/usr/bin/env python3
"""EXP-10B.2: deterministic three-center farthest-first clustered masks.

This module only rebuilds authorization masks and their exact filtered GT from
the already generated local embeddings. It does not regenerate embeddings,
rebuild HNSW, or touch original EXP-10B artifacts.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "experiment_config.json"
B2_CFG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "exp10b2_config.json"
EMB_DIR = ROOT / "data" / "exp10_fiqa_embeddings"
OUT_DIR = ROOT / "results" / "exp10b2"
MASK_DIR = OUT_DIR / "masks"
K = 10


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_f32(path: Path, rows: int, dim: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<f4")
    if arr.size != rows * dim:
        raise RuntimeError(f"{path.name}: expected {rows * dim} floats, got {arr.size}")
    return arr.reshape(rows, dim)


def exact_topk(scores: np.ndarray, mask: np.ndarray, k: int = K) -> tuple[np.ndarray, list[dict[str, Any]], list[int]]:
    work = scores if mask is None else np.where(mask[None, :], scores, -np.inf)
    order = np.argsort(-work, axis=1, kind="stable")[:, :k]
    boundary: list[dict[str, Any]] = []
    available: list[int] = []
    for i in range(work.shape[0]):
        row = work[i]
        aid = int(order[i, 0]) if k and np.isfinite(row[order[i, 0]]) else -1
        avail = int(np.count_nonzero(np.isfinite(row)))
        available.append(avail)
        if aid < 0:
            boundary.append({"boundary_score": None, "tie_count": 0, "topk_complete": False})
            continue
        boundary_score = float(row[order[i, k - 1]])
        tie_count = int(np.count_nonzero(row == row[order[i, k - 1]]))
        boundary.append(
            {
                "boundary_score": boundary_score,
                "tie_count": tie_count,
                "topk_complete": avail >= k,
                "tie_rule": "stable by corpus row index",
            }
        )
    return order.astype(np.int32), boundary, available


def ceil_sizes(n: int, selectivities: list[float]) -> dict[str, int]:
    return {f"{sel:g}": int(math.ceil(float(sel) * n)) for sel in selectivities}


def choose_three_centers(corpus: np.ndarray, seed: int) -> list[int]:
    """Deterministic farthest-first center selection from corpus rows only."""
    n = corpus.shape[0]
    rng = np.random.default_rng(int(seed))
    first = int(rng.choice(n))
    centers = [first]
    min_dist = np.clip(2.0 - 2.0 * (corpus.astype(np.float32) @ corpus[first].astype(np.float32)), 0.0, None)
    for _ in range(2):
        max_dist = float(np.max(min_dist))
        tied = np.flatnonzero(min_dist == max_dist)
        nxt = int(tied[0])  # smallest corpus row index breaks ties
        centers.append(nxt)
        dist = np.clip(2.0 - 2.0 * (corpus.astype(np.float32) @ corpus[nxt].astype(np.float32)), 0.0, None)
        min_dist = np.minimum(min_dist, dist)
    return centers


def assign_clusters(corpus: np.ndarray, centers: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Return labels and squared distances to the assigned center.

    Higher dot product means lower squared Euclidean distance for normalized
    vectors. np.argmax picks the earliest center on exact ties.
    """
    centers_arr = corpus[centers].astype(np.float32)
    sims = corpus.astype(np.float32) @ centers_arr.T
    labels = np.argmax(sims, axis=1).astype(np.int16)
    chosen_sim = sims[np.arange(corpus.shape[0]), labels]
    dist = np.clip(2.0 - 2.0 * chosen_sim, 0.0, None).astype(np.float32)
    return labels, dist


def build_three_center_mask(corpus: np.ndarray, target: int, seed: int) -> tuple[np.ndarray, dict[str, Any]]:
    if target < 0 or target > corpus.shape[0]:
        raise ValueError(f"target outside corpus range: {target}")
    centers = choose_three_centers(corpus, seed)
    labels, dist = assign_clusters(corpus, centers)
    mask = np.zeros(corpus.shape[0], dtype=bool)
    filled = 0
    partial: list[dict[str, Any]] = []
    for order, center_row in enumerate(centers):
        idx = np.flatnonzero(labels == order)
        if filled + idx.size <= target:
            mask[idx] = True
            filled += int(idx.size)
            continue
        need = target - filled
        if need < 0:
            raise RuntimeError("negative remaining mask capacity")
        # Squared distance ascending, then corpus row index ascending.
        order_idx = np.lexsort((idx, dist[idx]))[:need]
        chosen = idx[order_idx]
        mask[chosen] = True
        partial.append(
            {
                "center_row": center_row,
                "cluster_order": order,
                "cluster_size": int(idx.size),
                "taken": int(need),
            }
        )
        filled += int(need)
        break
    if filled != target:
        raise RuntimeError(f"three-center mask failed to fill target {target}: got {filled}")
    return mask, {
        "centers": centers,
        "cluster_sizes": [int(np.count_nonzero(labels == i)) for i in range(len(centers))],
        "center_selection": "farthest-first; initial row = default_rng(seed).choice(N); ties -> smallest row index",
        "assignment": "max dot product on normalized embeddings; ties -> earliest center in selection order",
        "cluster_order": "farthest-first center selection order",
        "partial_cluster": "distance squared to center ascending; ties -> smallest corpus row index",
        "partial_details": partial,
    }


def build_cluster3_artifacts() -> dict[str, Any]:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    b2cfg = json.loads(B2_CFG_PATH.read_text(encoding="utf-8"))
    emb_manifest = json.loads((EMB_DIR / "embedding_manifest.json").read_text(encoding="utf-8"))
    gt_manifest = json.loads((EMB_DIR / "gt_manifest.json").read_text(encoding="utf-8"))
    n = int(emb_manifest["counts"]["corpus"])
    nq = int(emb_manifest["counts"]["test_queries"])
    dim = int(cfg["model"]["dim"])
    corpus = load_f32(EMB_DIR / "corpus.f32", n, dim)
    queries = load_f32(EMB_DIR / "test_queries.f32", nq, dim)
    qids = (EMB_DIR / "test_query_ids.txt").read_text(encoding="utf-8").splitlines()
    corpus_ids = (EMB_DIR / "corpus_ids.txt").read_text(encoding="utf-8").splitlines()
    if len(qids) != nq or len(corpus_ids) != n:
        raise RuntimeError("embedding ID counts do not match manifests")

    print("[cluster3] computing exact query-corpus scores from existing embeddings", flush=True)
    scores = np.asarray(queries @ corpus.T, dtype=np.float32)

    selectivities = cfg["masks"]["selectivities"]
    seeds = b2cfg["mask_variants"]["new_three_center"]["seeds"]
    sizes = ceil_sizes(n, selectivities)
    MASK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gt_new: dict[str, Any] = {}
    masks: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        for sel in selectivities:
            pct = int(round(float(sel) * 100))
            target = sizes[f"{sel:g}"]
            mask, rule = build_three_center_mask(corpus, target, seed)
            key = f"cluster3_s{seed}_p{pct:02d}"
            path = MASK_DIR / f"mask_{key}.npy"
            np.save(path, mask)
            topk, boundary, available = exact_topk(scores, mask)
            gt_new[key] = {
                "topk": topk.tolist(),
                "boundary": boundary,
                "available": available,
                "authorized_docs": int(mask.sum()),
            }
            masks[key] = {
                "mask_type": "clustered_3center_farthest_first",
                "mask_key": key,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(path),
                "seed": int(seed),
                "selectivity": float(sel),
                "authorized_docs": int(mask.sum()),
                "rule": rule,
            }
            print(f"[cluster3] {key} size={int(mask.sum())} target={target}", flush=True)

    gt_path = OUT_DIR / "cluster3_filtered_gt.json"
    gt_path.write_text(
        json.dumps(
            {
                "query_ids": qids,
                "score_rule": gt_manifest["score_rule"],
                "masks": gt_new,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    old_variant = b2cfg["mask_variants"]["renamed_legacy"]
    old_mask_hashes = {
        key: sha256_file(EMB_DIR / f"mask_{key}.npy")
        for key in gt_manifest["masks"]
    }
    manifest = {
        "experiment": "EXP-10B.2",
        "source_embeddings": {
            "path": "data/exp10_fiqa_embeddings/corpus.f32",
            "sha256": sha256_file(EMB_DIR / "corpus.f32"),
            "regenerated": False,
        },
        "corpus_count": n,
        "query_count": nq,
        "k": K,
        "cardinality_rule": "ceil(selectivity * N)",
        "sizes": sizes,
        "mask_variants": {
            old_variant["new_name"]: {
                "old_name_in_exp10b1": old_variant["old_name"],
                "cardinality_rule": old_variant["cardinality_rule"],
                "sha256_by_mask_key": {
                    key: old_mask_hashes[key]
                    for key in old_mask_hashes
                    if key.startswith("clustered_")
                },
                "overwritten": False,
            },
            "clustered_3center_farthest_first": b2cfg["mask_variants"]["new_three_center"],
        },
        "masks": masks,
        "files": {
            "cluster3_filtered_gt.json": {
                "path": gt_path.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(gt_path),
                "size_bytes": gt_path.stat().st_size,
            }
        },
        "original_zip_md5_status": "NOT_VERIFIED",
    }
    manifest_path = OUT_DIR / "cluster_mask_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "cfg": cfg,
        "b2cfg": b2cfg,
        "n": n,
        "nq": nq,
        "dim": dim,
        "qids": qids,
        "corpus_ids": corpus_ids,
        "corpus": corpus,
        "queries": queries,
        "scores": scores,
        "selectivities": selectivities,
        "seeds": seeds,
        "sizes": sizes,
        "gt_new": gt_new,
        "masks": masks,
        "manifest": manifest,
    }


if __name__ == "__main__":
    ctx = build_cluster3_artifacts()
    print(
        f"[cluster3] wrote {len(ctx['masks'])} masks and manifest to {OUT_DIR.relative_to(ROOT).as_posix()}",
        flush=True,
    )
