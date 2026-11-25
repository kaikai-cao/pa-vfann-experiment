#!/usr/bin/env python3
"""EXP-10B.1: prefix recall, Oracle Prefix, qrels nDCG and bootstrap analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "experiments" / "exp10_fiqa_hnswlib" / "experiment_config.json"
EMB_DIR = ROOT / "data" / "exp10_fiqa_embeddings"
RAW_DIR = ROOT / "results" / "raw"
OUT_DIR = ROOT / "results"
FIG_DIR = ROOT / "results" / "figures"
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


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_qrels(path: Path) -> dict[str, list[tuple[int, float]]]:
    qrels: dict[str, list[tuple[int, float]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        if header != ["query-id", "corpus-id", "score"]:
            raise RuntimeError(f"qrels header mismatch: {header}")
        for qid, cid, gain in reader:
            qrels[qid].append((int(cid), float(gain)))
    return qrels


def dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ci_boot(values: np.ndarray, idx: np.ndarray) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=np.float64)
    means = arr[idx].mean(axis=1)
    return float(arr.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def mask_meta(key: str) -> tuple[str, int, float]:
    parts = key.split("_")
    kind = parts[0]
    seed = int(parts[1][1:])
    pct = int(parts[2][1:])
    return kind, seed, pct / 100.0


def main() -> None:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    data_manifest = json.loads((ROOT / "data" / "exp10_fiqa_manifest.json").read_text(encoding="utf-8"))
    emb_manifest = json.loads((EMB_DIR / "embedding_manifest.json").read_text(encoding="utf-8"))
    gt_manifest = json.loads((EMB_DIR / "gt_manifest.json").read_text(encoding="utf-8"))
    smoke_validation = json.loads((RAW_DIR / "exp10_fiqa_smoke" / "exp10_fiqa_smoke_validation.json").read_text(encoding="utf-8"))
    if smoke_validation.get("verdict") != "PASS":
        raise RuntimeError("C++ smoke validation is not PASS")

    n = int(emb_manifest["counts"]["corpus"])
    nq = int(emb_manifest["counts"]["test_queries"])
    dim = int(cfg["model"]["dim"])
    qids = (EMB_DIR / "test_query_ids.txt").read_text(encoding="utf-8").splitlines()
    corpus_ids = (EMB_DIR / "corpus_ids.txt").read_text(encoding="utf-8").splitlines()
    if len(corpus_ids) != n:
        raise RuntimeError("corpus ID count mismatch")
    corpus_id_to_row = {cid: i for i, cid in enumerate(corpus_ids)}
    corpus = load_f32(EMB_DIR / "corpus.f32", n, dim)
    queries = load_f32(EMB_DIR / "test_queries.f32", nq, dim)
    gt_u = json.loads((EMB_DIR / "gt_unfiltered.json").read_text(encoding="utf-8"))
    gt_f = json.loads((EMB_DIR / "gt_filtered.json").read_text(encoding="utf-8"))
    qrels = read_qrels(ROOT / data_manifest["components"]["qrels"]["path"])

    # HNSW top-k and trace summary.
    hnsw_topk: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in read_jsonl(RAW_DIR / "exp10_fiqa_hnsw_topk.jsonl"):
        hnsw_topk[(int(row["ef_search"]), int(row["query_index"]))].append(int(row["external_id"]))
    summary: dict[tuple[int, int], dict[str, Any]] = {}
    for row in read_jsonl(RAW_DIR / "exp10_fiqa_probe_summary.jsonl"):
        summary[(int(row["ef_search"]), int(row["query_index"]))] = row
    if len(hnsw_topk) != 3 * nq or len(summary) != 3 * nq:
        raise RuntimeError("incomplete HNSW top-k or summary output")

    # Unique first-touch trace: (ef, query) -> authorized-agnostic external IDs in order.
    first_touch: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in read_jsonl(RAW_DIR / "exp10_fiqa_first_touch.jsonl"):
        first_touch[(int(row["ef_search"]), int(row["query_index"]))].append(int(row["external_id"]))
    for key, ids in first_touch.items():
        if len(ids) != int(summary[key]["unique_count"]):
            raise RuntimeError(f"first-touch length mismatch for {key}")
        if len(set(ids)) != len(ids):
            raise RuntimeError(f"first-touch contains duplicate IDs for {key}")

    # Unfiltered Recall@10 and trace-cost table.
    unfiltered_rows: list[dict[str, Any]] = []
    for ef in cfg["hnsw"]["ef_search"]:
        recalls = []
        for qi in range(nq):
            pred = set(hnsw_topk[(ef, qi)])
            truth = set(gt_u["topk"][qi])
            recalls.append(len(pred & truth) / K)
            unfiltered_rows.append(
                {
                    "ef_search": ef,
                    "query_index": qi,
                    "qid": qids[qi],
                    "unfiltered_recall10": len(pred & truth) / K,
                    "event_count": int(summary[(ef, qi)]["event_count"]),
                    "unique_count": int(summary[(ef, qi)]["unique_count"]),
                }
            )
        print(f"[unfiltered] ef={ef} mean_recall10={np.mean(recalls):.4f}", flush=True)
    df_unfiltered = pd.DataFrame(unfiltered_rows)
    df_unfiltered.to_csv(OUT_DIR / "exp10_fiqa_unfiltered_recall.csv", index=False)

    # Recall gate: pre-registered rule, three efSearch all below 0.90 stops Oracle conclusions.
    ef_means = {int(ef): float(v) for ef, v in df_unfiltered.groupby("ef_search")["unfiltered_recall10"].mean().items()}
    all_below = all(value < 0.90 for value in ef_means.values())
    low_quality = [ef for ef, value in ef_means.items() if value < 0.90]
    gate = {
        "rule": cfg["recall_gate"]["rule"],
        "threshold": 0.90,
        "mean_unfiltered_recall10": ef_means,
        "all_below_threshold": all_below,
        "oracle_main_conclusion": "STOP" if all_below else "CONTINUE",
        "low_quality_configs": low_quality,
    }
    (OUT_DIR / "exp10_fiqa_recall_gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    prefix_fracs = cfg["prefixes"]["budget_fractions"]
    deltas = cfg["prefixes"]["oracle_delta"]
    boots = cfg["statistics"]["resamples"]
    boot_rng = np.random.default_rng(int(cfg["statistics"]["seed"]))
    bootstrap_idx = boot_rng.integers(0, nq, size=(boots, nq))

    records: list[dict[str, Any]] = []
    oracle_records: list[dict[str, Any]] = []

    for key in gt_f:
        kind, seed, sel = mask_meta(key)
        mask = np.load(EMB_DIR / f"mask_{key}.npy", allow_pickle=False)
        if not np.issubdtype(mask.dtype, np.bool_) or int(mask.sum()) != gt_f[key]["authorized_docs"]:
            raise RuntimeError(f"mask mismatch: {key}")
        truth_sets = [set(map(int, row)) for row in gt_f[key]["topk"]]

        # Precompute exact-score order among qrel-relevant authorized docs for nDCG.
        rel_info: list[tuple[list[int], dict[int, float], float]] = []
        for qi, qid in enumerate(qids):
            rel_pairs: list[tuple[int, float]] = []
            for cid_text, gain in qrels.get(qid, []):
                row = corpus_id_to_row.get(cid_text)
                if row is not None and mask[row]:
                    rel_pairs.append((row, gain))
            score_map: dict[int, float] = {}
            gain_map: dict[int, float] = {}
            for cid, gain in rel_pairs:
                score_map[cid] = float(np.dot(queries[qi], corpus[cid]))
                gain_map[cid] = gain
            score_order = sorted(score_map, key=lambda cid: (-score_map[cid], cid))[:K]
            ideal_order = sorted(gain_map, key=lambda cid: (-gain_map[cid], cid))[:K]
            idcg = dcg([gain_map[cid] for cid in ideal_order])
            rel_info.append((score_order, gain_map, idcg))

        for ef in cfg["hnsw"]["ef_search"]:
            for qi, qid in enumerate(qids):
                ft = first_touch[(ef, qi)]
                B = len(ft)
                t_min = max(1, math.ceil(0.60 * B))
                ft_arr = np.asarray(ft, dtype=np.int64)
                gt_set = truth_sets[qi]
                hits = np.fromiter((1 if int(e) in gt_set else 0 for e in ft_arr), dtype=np.int8, count=B)
                cum = np.cumsum(hits)
                r_full = int(cum[-1]) / K if B else 0.0

                score_order, gain_map, idcg = rel_info[qi]
                row: dict[str, Any] = {
                    "ef_search": ef,
                    "query_index": qi,
                    "qid": qid,
                    "mask_key": key,
                    "mask_type": kind,
                    "seed": seed,
                    "selectivity": sel,
                    "B": B,
                    "authorized_docs": int(mask.sum()),
                    "authorized_in_trace": int(mask[ft_arr].sum()),
                    "prefix_recall_full": r_full,
                }
                for frac in prefix_fracs:
                    t = min(B, max(1, math.ceil(frac * B)))
                    recall = int(cum[t - 1]) / K if B else 0.0
                    col = f"prefix_recall_{int(round(frac * 100)):02d}"
                    row[col] = recall
                    row[f"prefix_t_{int(round(frac * 100)):02d}"] = t
                    cand = set(int(e) for e in ft_arr[:t])
                    if idcg > 0:
                        gains = [gain_map[cid] for cid in score_order if cid in cand][:K]
                        row[f"ndcg_{int(round(frac * 100)):02d}"] = dcg(gains) / idcg
                    else:
                        row[f"ndcg_{int(round(frac * 100)):02d}"] = 0.0
                row["ndcg_full"] = row["ndcg_100"]

                for delta in deltas:
                    need = math.ceil(int(cum[-1]) - K * delta)
                    tail = cum[t_min - 1 :]
                    pos = int(np.searchsorted(tail, need)) if tail.size else -1
                    if pos < tail.size and tail.size:
                        t_star = t_min + pos
                        reached = True
                    else:
                        t_star = B
                        reached = False
                    tag = f"{int(round(delta * 100)):02d}"
                    row[f"oracle_t_{tag}"] = t_star
                    row[f"oracle_ratio_{tag}"] = t_star / B if B else 1.0
                    row[f"oracle_reached_{tag}"] = reached
                    oracle_records.append(
                        {
                            "ef_search": ef,
                            "query_index": qi,
                            "qid": qid,
                            "mask_key": key,
                            "mask_type": kind,
                            "seed": seed,
                            "selectivity": sel,
                            "delta": delta,
                            "B": B,
                            "t_star": t_star,
                            "ratio": t_star / B if B else 1.0,
                            "reached": reached,
                            "recall_at_B": r_full,
                        }
                    )
                records.append(row)

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "exp10_fiqa_prefix_recall.csv", index=False)
    pd.DataFrame(oracle_records).to_csv(OUT_DIR / "exp10_fiqa_oracle_prefix.csv", index=False)

    # Bootstrap CIs, paired by query index within each group.
    bootstrap_rows: list[dict[str, Any]] = []

    def add_boot(group_name: str, subset: pd.DataFrame, filt: dict[str, Any]) -> None:
        if subset.empty:
            return
        for metric in (
            "unfiltered_recall10",
            "prefix_recall_60",
            "prefix_recall_80",
            "prefix_recall_90",
            "prefix_recall_full",
            "ndcg_80",
            "ndcg_full",
            "oracle_ratio_05",
            "oracle_ratio_10",
        ):
            if metric not in subset:
                continue
            vals = subset[metric].to_numpy(dtype=np.float64)
            if vals.size != nq:
                # For mask-specific groups subset still has one row per query.
                if vals.size < 2:
                    continue
            mean, low, high = ci_boot(vals, bootstrap_idx[:, : vals.size])
            bootstrap_rows.append(
                {
                    "group": group_name,
                    **filt,
                    "metric": metric,
                    "n_queries": int(vals.size),
                    "mean": mean,
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    for ef in cfg["hnsw"]["ef_search"]:
        sub_u = df_unfiltered[df_unfiltered["ef_search"] == ef]
        add_boot("unfiltered_by_ef", sub_u, {"ef_search": ef})
        for key in gt_f:
            kind, seed, sel = mask_meta(key)
            add_boot(
                "mask_by_ef",
                df[(df["ef_search"] == ef) & (df["mask_key"] == key)],
                {"ef_search": ef, "mask_type": kind, "seed": seed, "selectivity": sel, "mask_key": key},
            )
        for kind in ("random", "clustered"):
            add_boot("mask_type", df[(df["ef_search"] == ef) & (df["mask_type"] == kind)], {"ef_search": ef, "mask_type": kind})
        for sel in cfg["masks"]["selectivities"]:
            add_boot("selectivity", df[(df["ef_search"] == ef) & (df["selectivity"] == sel)], {"ef_search": ef, "selectivity": sel})
        for seed in cfg["masks"]["seeds"]:
            add_boot("seed", df[(df["ef_search"] == ef) & (df["seed"] == seed)], {"ef_search": ef, "seed": seed})
        add_boot(
            "low_selectivity",
            df[(df["ef_search"] == ef) & (df["selectivity"] == 0.01)],
            {"ef_search": ef, "selectivity": 0.01},
        )

    df_boot = pd.DataFrame(bootstrap_rows)
    df_boot.to_csv(OUT_DIR / "exp10_fiqa_bootstrap.csv", index=False)

    # Figures.
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "axes.grid": True, "grid.alpha": 0.3})

    fig, ax = plt.subplots(figsize=(8, 5))
    for ef, g in df_unfiltered.groupby("ef_search"):
        ax.bar([str(ef) + " (mean)"], [g["unfiltered_recall10"].mean()], label=f"ef={ef}")
    ax.axhline(0.90, color="firebrick", linestyle="--", linewidth=1, label="0.90 gate")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Unfiltered Recall@10")
    ax.set_title("EXP-10B.1 unfiltered exact Recall@10 gate")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig01_unfiltered_recall_gate.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for ef in cfg["hnsw"]["ef_search"]:
        g = df[df["ef_search"] == ef]
        ax.plot(["60%", "80%", "90%", "100%"], [g[f"prefix_recall_{p}"].mean() for p in ("60", "80", "90", "full")], marker="o", label=f"ef={ef}")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Filtered candidate Recall@10")
    ax.set_title("Prefix recall by HNSW budget fraction")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig02_prefix_recall_curve.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    g = df_boot[(df_boot["group"] == "low_selectivity") & (df_boot["metric"] == "prefix_recall_full")]
    for _, r in g.iterrows():
        ax.errorbar(
            [r["ef_search"]],
            [r["mean"]],
            yerr=[[abs(r["mean"] - r["ci_low"])], [abs(r["ci_high"] - r["mean"])]],
            fmt="o",
            capsize=4,
        )
    ax.set_ylabel("Recall@10 at full trace (1% masks)")
    ax.set_title("1% selectivity is the hard regime")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig03_low_selectivity.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    g = df_boot[(df_boot["group"] == "mask_type") & (df_boot["metric"] == "prefix_recall_80") & (df_boot["ef_search"] == 128)]
    labels = [f"{r['mask_type']} p{int(round(r['selectivity'] * 100))}" if "selectivity" in r and pd.notna(r.get("selectivity")) else str(r["mask_type"]) for _, r in g.iterrows()]
    ax.bar(range(len(g)), [r["mean"] for _, r in g.iterrows()], yerr=[r["ci_high"] - r["ci_low"] for _, r in g.iterrows()], capsize=4)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Prefix Recall@10 at 80%")
    ax.set_title("Random vs embedding-clustered masks (ef=128)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig04_random_vs_clustered.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for delta, tag in ((0.05, "05"), (0.10, "10")):
        g = df[df["selectivity"] == 0.10]
        ax.hist(g[f"oracle_ratio_{tag}"], bins=30, alpha=0.5, label=f"delta={delta}")
    ax.set_xlabel("t* / B")
    ax.set_ylabel("queries x masks")
    ax.set_title("Oracle Prefix ratio distribution (10% masks)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig05_oracle_distribution.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for ef, g in df_unfiltered.groupby("ef_search"):
        ax.bar([f"ef={ef} events"], [g["event_count"].mean()], alpha=0.7)
        ax.bar([f"ef={ef} unique"], [g["unique_count"].mean()], alpha=0.7)
    ax.set_ylabel("mean distance evaluations per query")
    ax.set_title("Trace cost by efSearch")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig06_trace_cost.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for ef in cfg["hnsw"]["ef_search"]:
        g = df[df["ef_search"] == ef]
        ax.plot(["60%", "80%", "90%", "100%"], [g[f"ndcg_{p}"].mean() for p in ("60", "80", "90", "full")], marker="o", label=f"ef={ef}")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Filtered qrels nDCG@10 (secondary)")
    ax.set_title("nDCG@10 by prefix budget")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig07_ndcg_curve.png", dpi=180)
    plt.close(fig)

    summary = {
        "experiment": cfg["experiment"],
        "data_gate": data_manifest["data_gate"],
        "original_zip_md5_status": data_manifest["original_zip_md5"]["status"],
        "smoke_validation": smoke_validation,
        "model": emb_manifest["model"],
        "hnsw": cfg["hnsw"],
        "recall_gate": gate,
        "unfiltered_mean_recall10": ef_means,
        "trace_cost": {
            str(ef): {
                "mean_event_count": float(df_unfiltered[df_unfiltered["ef_search"] == ef]["event_count"].mean()),
                "mean_unique_count": float(df_unfiltered[df_unfiltered["ef_search"] == ef]["unique_count"].mean()),
            }
            for ef in cfg["hnsw"]["ef_search"]
        },
        "prefix_recall": {
            str(ef): {
                str(frac): float(df[df["ef_search"] == ef][f"prefix_recall_{int(round(frac * 100)):02d}"].mean())
                for frac in prefix_fracs
            }
            for ef in cfg["hnsw"]["ef_search"]
        },
        "oracle_ratio": {
            str(ef): {
                str(delta): float(df[df["ef_search"] == ef][f"oracle_ratio_{int(round(delta * 100)):02d}"].mean())
                for delta in deltas
            }
            for ef in cfg["hnsw"]["ef_search"]
        },
        "group_highlights": {
            "low_selectivity_full_recall": {
                str(ef): float(
                    df[(df["ef_search"] == ef) & (df["selectivity"] == 0.01)]["prefix_recall_full"].mean()
                )
                for ef in cfg["hnsw"]["ef_search"]
            },
            "mask_type_full_recall": {
                str(kind): float(df[df["mask_type"] == kind]["prefix_recall_full"].mean())
                for kind in ("random", "clustered")
            },
        },
        "artifacts": {
            name: {"path": str((OUT_DIR / name).relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(OUT_DIR / name)}
            for name in (
                "exp10_fiqa_unfiltered_recall.csv",
                "exp10_fiqa_prefix_recall.csv",
                "exp10_fiqa_oracle_prefix.csv",
                "exp10_fiqa_bootstrap.csv",
                "exp10_fiqa_recall_gate.json",
            )
        },
        "gt_manifest_sha256": sha256_file(EMB_DIR / "gt_manifest.json"),
        "data_manifest_sha256": sha256_file(ROOT / "data" / "exp10_fiqa_manifest.json"),
    }
    (OUT_DIR / "exp10_fiqa_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[analysis] rows={len(df)} bootstrap_rows={len(df_boot)} figures=7", flush=True)


if __name__ == "__main__":
    main()
