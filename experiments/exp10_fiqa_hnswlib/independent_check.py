#!/usr/bin/env python3
"""Independent sample-level recomputation from raw traces, masks and GT."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EMB_DIR = ROOT / "data" / "exp10_fiqa_embeddings"
RAW_DIR = ROOT / "results" / "raw"
OUT = ROOT / "results" / "exp10_fiqa_independent_check.json"
SAMPLE_Q = [0, 17, 123, 321, 647]
SAMPLE_MASKS = ["random_s2026_p01", "clustered_s2027_p10", "random_s2028_p30"]
SAMPLE_EF = [64, 128, 256]
PREFIXES = ("60", "80", "full")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    gt = load_json(EMB_DIR / "gt_filtered.json")
    qids = (EMB_DIR / "test_query_ids.txt").read_text(encoding="utf-8").splitlines()
    df = pd.read_csv(ROOT / "results" / "exp10_fiqa_prefix_recall.csv")
    df["qid"] = df["qid"].astype(str)
    wanted = {(ef, qi) for ef in SAMPLE_EF for qi in SAMPLE_Q}
    ft: dict[tuple[int, int], list[int]] = {(ef, qi): [] for ef, qi in wanted}
    with (RAW_DIR / "exp10_fiqa_first_touch.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (int(row["ef_search"]), int(row["query_index"]))
            if key in ft:
                ft[key].append(int(row["external_id"]))

    checks = []
    for ef in SAMPLE_EF:
        for qi in SAMPLE_Q:
            trace = ft[(ef, qi)]
            B = len(trace)
            for mask_key in SAMPLE_MASKS:
                mask = np.load(EMB_DIR / f"mask_{mask_key}.npy", allow_pickle=False)
                truth = set(gt[mask_key]["topk"][qi])
                hits = [1 if int(e) in truth else 0 for e in trace]
                for tag in PREFIXES:
                    col_tag = "100" if tag == "full" else tag
                    t_col = f"prefix_t_{col_tag}"
                    r_col = f"prefix_recall_{col_tag}"
                    csv_row = df[(df["ef_search"] == ef) & (df["qid"] == qids[qi]) & (df["mask_key"] == mask_key)].iloc[0]
                    t = int(csv_row[t_col])
                    recomputed = sum(hits[: min(t, B)]) / 10.0
                    stored = float(csv_row[r_col])
                    checks.append(
                        {
                            "ef_search": ef,
                            "qid": qids[qi],
                            "mask_key": mask_key,
                            "prefix": tag,
                            "recomputed": recomputed,
                            "stored": stored,
                            "match": abs(recomputed - stored) < 1e-12,
                        }
                    )

    # Unfiltered recall spot check from HNSW top-k against exact GT.
    gt_u = load_json(EMB_DIR / "gt_unfiltered.json")
    hnsw_topk: dict[tuple[int, int], set[int]] = {}
    with (RAW_DIR / "exp10_fiqa_hnsw_topk.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (int(row["ef_search"]), int(row["query_index"]))
            if key in wanted:
                hnsw_topk.setdefault(key, set()).add(int(row["external_id"]))
    for ef in SAMPLE_EF:
        for qi in SAMPLE_Q:
            recomputed = len(hnsw_topk[(ef, qi)] & set(gt_u["topk"][qi])) / 10.0
            stored = float(
                pd.read_csv(ROOT / "results" / "exp10_fiqa_unfiltered_recall.csv")
                .query("ef_search == @ef and query_index == @qi")["unfiltered_recall10"]
                .iloc[0]
            )
            checks.append(
                {
                    "ef_search": ef,
                    "qid": qids[qi],
                    "mask_key": "UNFILTERED",
                    "prefix": "full",
                    "recomputed": recomputed,
                    "stored": stored,
                    "match": abs(recomputed - stored) < 1e-12,
                }
            )

    out = {
        "method": "independent sample-level recomputation from raw first-touch and top-k files",
        "sample_query_indices": SAMPLE_Q,
        "sample_masks": SAMPLE_MASKS,
        "sample_ef_search": SAMPLE_EF,
        "checks": len(checks),
        "all_match": all(c["match"] for c in checks),
        "failed": [c for c in checks if not c["match"]],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[independent-check] checks={len(checks)} all_match={out['all_match']}")
    if not out["all_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
