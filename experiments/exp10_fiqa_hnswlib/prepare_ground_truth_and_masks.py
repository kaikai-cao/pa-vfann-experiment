#!/usr/bin/env python3
"""EXP-10B.1: exact ground truth and 18 synthetic authorization masks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import numpy as np
from sklearn.cluster import MiniBatchKMeans

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "experiment_config.json"
EMB_DIR = ROOT / "data" / "exp10_fiqa_embeddings"
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


def exact_topk(scores: np.ndarray, mask: np.ndarray | None = None) -> tuple[np.ndarray, list[dict[str, Any]], list[int]]:
    work = scores if mask is None else np.where(mask[None, :], scores, -np.inf)
    order = np.argsort(-work, axis=1, kind="stable")[:, :K]
    boundary: list[dict[str, Any]] = []
    available: list[int] = []
    for i in range(work.shape[0]):
        row = work[i]
        aid = int(order[i, 0]) if K and np.isfinite(row[order[i, 0]]) else -1
        avail = int(np.count_nonzero(np.isfinite(row)))
        available.append(avail)
        if aid < 0:
            boundary.append({"boundary_score": None, "tie_count": 0, "topk_complete": False})
            continue
        boundary_score = float(row[order[i, K - 1]])
        tie_count = int(np.count_nonzero(row == row[order[i, K - 1]]))
        boundary.append(
            {
                "boundary_score": boundary_score,
                "tie_count": tie_count,
                "topk_complete": avail >= K,
                "tie_rule": "stable by corpus row index",
            }
        )
    return order.astype(np.int32), boundary, available


def random_mask(n: int, size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mask = np.zeros(n, dtype=bool)
    mask[rng.choice(n, size=size, replace=False)] = True
    return mask


def clustered_masks(
    corpus: np.ndarray,
    sizes: list[int],
    seed: int,
    cfg: dict[str, Any],
) -> list[np.ndarray]:
    algo = cfg["masks"]["clustered_rule"]
    n = corpus.shape[0]
    n_clusters = int(algo["n_clusters"])
    km = MiniBatchKMeans(
        n_clusters=n_clusters,
        random_state=seed,
        n_init=int(algo["n_init"]),
        batch_size=int(algo["batch_size"]),
        max_iter=100,
    )
    labels = km.fit_predict(corpus)
    centroids = np.asarray(km.cluster_centers_, dtype=np.float64)
    direction_rng = np.random.default_rng(seed + 10000)
    direction = direction_rng.normal(size=corpus.shape[1]).astype(np.float64)
    direction /= np.linalg.norm(direction)
    cluster_score = centroids @ direction
    cluster_order = np.argsort(-cluster_score, kind="stable")

    masks: list[np.ndarray] = []
    for target in sizes:
        mask = np.zeros(n, dtype=bool)
        count = 0
        for c in cluster_order:
            idx = np.where(labels == c)[0]
            if count + idx.size <= target:
                mask[idx] = True
                count += idx.size
                if count == target:
                    break
                continue
            need = target - count
            centroid = centroids[c]
            dist = np.linalg.norm(corpus[idx].astype(np.float64) - centroid, axis=1)
            chosen = idx[np.lexsort((idx, dist))[:need]]
            mask[chosen] = True
            count += need
            break
        if count != target:
            raise RuntimeError(f"clustered mask failed to fill target {target}: got {count}")
        masks.append(mask)
    return masks


def main() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    emb_manifest = json.loads((EMB_DIR / "embedding_manifest.json").read_text(encoding="utf-8"))
    dim = int(cfg["model"]["dim"])
    n = int(emb_manifest["counts"]["corpus"])
    nq = int(emb_manifest["counts"]["test_queries"])
    corpus = load_f32(EMB_DIR / "corpus.f32", n, dim)
    queries = load_f32(EMB_DIR / "test_queries.f32", nq, dim)
    qids = (EMB_DIR / "test_query_ids.txt").read_text(encoding="utf-8").splitlines()
    if len(qids) != nq:
        raise RuntimeError("query ID count mismatch")

    print("[scores] computing exact unfiltered scores", flush=True)
    scores = np.asarray(queries @ corpus.T, dtype=np.float32)
    unfiltered_topk, unfiltered_boundary, unfiltered_available = exact_topk(scores)

    gt_unfiltered = {
        "query_ids": qids,
        "topk": unfiltered_topk.tolist(),
        "boundary": unfiltered_boundary,
        "available": unfiltered_available,
    }
    (EMB_DIR / "gt_unfiltered.json").write_text(
        json.dumps(gt_unfiltered, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    selectivities = cfg["masks"]["selectivities"]
    seeds = cfg["masks"]["seeds"]
    sizes = [int(round(s * n)) for s in selectivities]
    files: dict[str, Any] = {}
    gt_filtered: dict[str, Any] = {}

    for seed in seeds:
        random_blocks = [random_mask(n, size, seed) for size in sizes]
        clustered_blocks = clustered_masks(corpus, sizes, seed, cfg["ground_truth"] | {"masks": cfg["masks"]})
        for kind, blocks in (("random", random_blocks), ("clustered", clustered_blocks)):
            for sel, size, mask in zip(selectivities, sizes, blocks):
                key = f"{kind}_s{seed}_p{int(round(sel * 100)):02d}"
                mask_path = EMB_DIR / f"mask_{key}.npy"
                np.save(mask_path, mask)
                print(f"[filtered-gt] {key} size={int(mask.sum())}", flush=True)
                topk, boundary, available = exact_topk(scores, mask)
                gt_filtered[key] = {
                    "topk": topk.tolist(),
                    "boundary": boundary,
                    "available": available,
                    "authorized_docs": int(mask.sum()),
                }
                files[key] = {
                    "mask": {"path": str(mask_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(mask_path)},
                    "selectivity": sel,
                    "seed": seed,
                    "authorized_docs": int(mask.sum()),
                }

    (EMB_DIR / "gt_filtered.json").write_text(
        json.dumps(gt_filtered, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    manifest = {
        "experiment": cfg["experiment"],
        "k": K,
        "score_rule": cfg["ground_truth"],
        "corpus_count": n,
        "query_count": nq,
        "mask_count": len(files),
        "mask_sizes_by_selectivity": dict(zip([str(s) for s in selectivities], sizes)),
        "masks": files,
        "files": {
            name: {
                "path": str((EMB_DIR / name).relative_to(ROOT)).replace("\\", "/"),
                "size_bytes": (EMB_DIR / name).stat().st_size,
                "sha256": sha256_file(EMB_DIR / name),
            }
            for name in ("gt_unfiltered.json", "gt_filtered.json")
        },
        "data_gate": "PASS_COMPONENT_ARTIFACTS",
        "original_zip_md5_status": "NOT_VERIFIED",
    }
    (EMB_DIR / "gt_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[gt-manifest] {len(files)} masks, unfiltered exact GT written", flush=True)


if __name__ == "__main__":
    main()
