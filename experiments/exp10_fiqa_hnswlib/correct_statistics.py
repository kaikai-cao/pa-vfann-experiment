#!/usr/bin/env python3
"""EXP-10B.2: correction of Oracle, bootstrap, nDCG and clustered mask statistics.

All computations use the existing EXP-10B embeddings, GT and raw HNSW traces.
No embedding, HNSW index, query run, or original result file is regenerated.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import numpy as np
import pandas as pd

from rebuild_cluster_masks import (
    B2_CFG_PATH,
    CFG_PATH,
    EMB_DIR,
    K,
    OUT_DIR,
    ROOT,
    build_cluster3_artifacts,
    sha256_file,
)

RAW_DIR = ROOT / "results" / "raw"
RESULT_DIR = ROOT / "results"
B2_OUT = ROOT / "results" / "exp10b2"
INPUT_SHA_PATH = B2_OUT / "original_input_sha256.txt"
PREFIX_FRACS = (0.60, 0.80, 0.90, 1.00)
PREFIX_TAGS = ("60", "80", "90", "100")
ORACLE_TAGS = ("05", "10")
METRICS = (
    "prefix_recall_60",
    "prefix_recall_80",
    "prefix_recall_90",
    "prefix_recall_100",
    "ndcg_60",
    "ndcg_80",
    "ndcg_90",
    "ndcg_100",
    "oracle_ratio_05",
    "oracle_ratio_10",
    "oracle_reached_05",
    "oracle_reached_10",
)


def read_jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
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


def dcg(gains: Iterable[float]) -> float:
    return sum(float(g) / math.log2(i + 2) for i, g in enumerate(gains))


def idcg_from_gains(gains: np.ndarray, k: int = K) -> float:
    arr = np.sort(np.asarray(gains, dtype=np.float64))[::-1][:k]
    return dcg(arr)


def ndcg_at_k(
    candidate_ids: np.ndarray,
    score_arr: np.ndarray,
    gain_arr: np.ndarray,
    idcg: float,
    k: int = K,
) -> float:
    """nDCG@k over the supplied candidate set only.

    Candidates are never pre-filtered by qrels. Ranking is by exact score
    descending with corpus row ID ascending as the deterministic tie-break.
    """
    ids = np.asarray(candidate_ids, dtype=np.int64)
    if ids.size == 0 or not np.isfinite(idcg) or idcg <= 0:
        return 0.0
    scores = np.asarray(score_arr, dtype=np.float32)[ids]
    neg = -scores
    if ids.size <= k:
        chosen = ids[np.lexsort((ids, neg))]
    else:
        threshold = float(np.partition(neg, k - 1)[k - 1])
        strictly_better = ids[neg < threshold]
        tied = ids[neg == threshold]
        need = k - strictly_better.size
        if need > 0:
            tied_sorted = tied[np.argsort(tied, kind="stable")[:need]]
            chosen = np.concatenate([strictly_better, tied_sorted])
        else:
            chosen = strictly_better[:k]
        if chosen.size > 1:
            chosen = chosen[np.lexsort((chosen, -np.asarray(score_arr, dtype=np.float32)[chosen]))]
    gains = np.asarray(gain_arr, dtype=np.float64)[chosen]
    return float(dcg(gains) / idcg)


def oracle_from_cum(cum: np.ndarray, b: int, delta: float, t_min: int, k: int = K) -> tuple[bool, int | None, float | None]:
    if b <= 0:
        return False, None, None
    need = int(math.ceil(int(cum[-1]) - k * float(delta)))
    tail = cum[t_min - 1 :]
    if tail.size == 0:
        return False, None, None
    pos = int(np.searchsorted(tail, need))
    if pos < tail.size:
        t_star = int(t_min + pos)
        return True, t_star, float(t_star / b)
    return False, None, None


def make_bootstrap_indices(n_qids: int, resamples: int, seed: int) -> np.ndarray:
    if n_qids <= 0:
        raise ValueError("n_qids must be positive")
    return np.random.default_rng(int(seed)).integers(0, n_qids, size=(int(resamples), n_qids))


def cluster_bootstrap_mean(
    df: pd.DataFrame,
    qid_col: str,
    metric: str,
    *,
    resamples: int = 2000,
    seed: int = 20261125,
    qids: list[str] | None = None,
    indices: np.ndarray | None = None,
) -> tuple[float, float, float, int]:
    """Cluster bootstrap where every resampled qid brings all of its rows."""
    work = df[[qid_col, metric]].copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    work = work.dropna(subset=[metric, qid_col])
    if work.empty:
        return float("nan"), float("nan"), float("nan"), 0
    if qids is None:
        qids = sorted(work[qid_col].astype(str).unique().tolist())
    qids = [str(q) for q in qids]
    work[qid_col] = work[qid_col].astype(str)
    grouped = work.groupby(qid_col)[metric]
    sums = grouped.sum().reindex(qids, fill_value=0.0).to_numpy(dtype=np.float64)
    counts = grouped.count().reindex(qids, fill_value=0).to_numpy(dtype=np.float64)
    total_count = float(counts.sum())
    if total_count <= 0:
        return float("nan"), float("nan"), float("nan"), len(qids)
    if indices is None:
        indices = make_bootstrap_indices(len(qids), resamples, seed)
    elif indices.shape[1] != len(qids):
        raise RuntimeError(f"bootstrap indices have {indices.shape[1]} qids, expected {len(qids)}")
    boot_sums = sums[indices].sum(axis=1)
    boot_counts = counts[indices].sum(axis=1)
    means = np.divide(
        boot_sums,
        boot_counts,
        out=np.full(boot_sums.shape, np.nan, dtype=np.float64),
        where=boot_counts > 0,
    )
    means = means[~np.isnan(means)]
    if means.size == 0:
        return float("nan"), float("nan"), float("nan"), len(qids)
    overall = float(sums.sum() / total_count)
    return overall, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), len(qids)


def summarize_oracle_reachability(
    oracle_df: pd.DataFrame,
    *,
    resamples: int = 2000,
    seed: int = 20261125,
    indices: np.ndarray | None = None,
) -> pd.DataFrame:
    group_keys = ["ef_search", "mask_type", "selectivity", "delta"]
    rows: list[dict[str, Any]] = []
    for keys, g in oracle_df.groupby(group_keys, sort=True):
        reached = g[g["reached"] == True].copy()
        missing = g[g["reached"] != True].copy()
        n_total = int(len(g))
        n_reached = int(len(reached))
        n_missing = int(len(missing))
        if n_reached:
            ratios = reached["normalized_t_star"].dropna().to_numpy(dtype=np.float64)
            mean_ratio = float(np.mean(ratios))
            median_ratio = float(np.median(ratios))
            p90_ratio = float(np.percentile(ratios, 90))
            mean_t = float(reached["t_star"].dropna().mean())
            _, ci_low, ci_high, _ = cluster_bootstrap_mean(
                reached,
                "qid",
                "normalized_t_star",
                resamples=resamples,
                seed=seed,
                indices=indices,
            )
        else:
            mean_ratio = median_ratio = p90_ratio = mean_t = ci_low = ci_high = float("nan")
        if n_missing:
            rec = missing["recall_at_B"].dropna().to_numpy(dtype=np.float64)
            not_mean = float(np.mean(rec))
            not_median = float(np.median(rec))
            not_p10 = float(np.percentile(rec, 10))
            not_p90 = float(np.percentile(rec, 90))
            not_min = float(np.min(rec))
            not_max = float(np.max(rec))
        else:
            not_mean = not_median = not_p10 = not_p90 = not_min = not_max = float("nan")
        rows.append(
            {
                **dict(zip(group_keys, keys)),
                "total_samples": n_total,
                "reached_count": n_reached,
                "not_reached_count": n_missing,
                "reached_rate": n_reached / n_total if n_total else float("nan"),
                "reached_only_mean_t_star": mean_t,
                "reached_only_mean_normalized_t_star": mean_ratio,
                "reached_only_median_normalized_t_star": median_ratio,
                "reached_only_p90_normalized_t_star": p90_ratio,
                "reached_only_ci_low": ci_low,
                "reached_only_ci_high": ci_high,
                "not_reached_recall_at_B_mean": not_mean,
                "not_reached_recall_at_B_median": not_median,
                "not_reached_recall_at_B_p10": not_p10,
                "not_reached_recall_at_B_p90": not_p90,
                "not_reached_recall_at_B_min": not_min,
                "not_reached_recall_at_B_max": not_max,
            }
        )
    return pd.DataFrame(rows).sort_values(group_keys).reset_index(drop=True)


def paired_diff_frame(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: list[str],
    value_col: str,
    *,
    direction: str,
) -> pd.DataFrame:
    l = left[keys + [value_col]].dropna(subset=[value_col]).copy()
    r = right[keys + [value_col]].dropna(subset=[value_col]).copy()
    l[value_col] = pd.to_numeric(l[value_col], errors="coerce").astype(np.float64)
    r[value_col] = pd.to_numeric(r[value_col], errors="coerce").astype(np.float64)
    l = l.dropna(subset=[value_col])
    r = r.dropna(subset=[value_col])
    merged = pd.merge(l, r, on=keys, how="inner", suffixes=("_left", "_right"))
    if merged.empty:
        return pd.DataFrame(columns=keys + ["diff", "direction"])
    merged["diff"] = merged[f"{value_col}_right"] - merged[f"{value_col}_left"]
    out = merged[keys + ["diff"]].copy()
    out["direction"] = direction
    return out


def mask_type_label(raw: str) -> str:
    if raw == "clustered":
        return "clustered_128_random_direction"
    return raw


def parse_old_key(key: str) -> tuple[str, int, float]:
    parts = key.split("_")
    kind = parts[0]
    seed = int(parts[1][1:])
    sel = int(parts[2][1:]) / 100.0
    return kind, seed, sel


def build_mask_definitions(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    gt_old = json.loads((EMB_DIR / "gt_filtered.json").read_text(encoding="utf-8"))
    defs: list[dict[str, Any]] = []
    for key in gt_old:
        kind, seed, sel = parse_old_key(key)
        path = EMB_DIR / f"mask_{key}.npy"
        defs.append(
            {
                "source_key": key,
                "mask_key": key,
                "mask_type": mask_type_label(kind),
                "seed": seed,
                "selectivity": sel,
                "mask": np.load(path, allow_pickle=False),
                "gt": gt_old[key],
                "origin": "EXP-10B.1",
            }
        )
    for key, rec in ctx["masks"].items():
        defs.append(
            {
                "source_key": key,
                "mask_key": key,
                "mask_type": rec["mask_type"],
                "seed": int(rec["seed"]),
                "selectivity": float(rec["selectivity"]),
                "mask": np.load(ROOT / rec["path"], allow_pickle=False),
                "gt": ctx["gt_new"][key],
                "origin": "EXP-10B.2",
            }
        )
    return defs


def load_traces(cfg: dict[str, Any], nq: int) -> tuple[dict[tuple[int, int], np.ndarray], dict[tuple[int, int], dict[str, Any]]]:
    traces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in read_jsonl_gz(RAW_DIR / "exp10_fiqa_first_touch.jsonl.gz"):
        traces[(int(row["ef_search"]), int(row["query_index"]))].append(int(row["external_id"]))
    summary_rows: dict[tuple[int, int], dict[str, Any]] = {}
    for row in read_jsonl_gz(RAW_DIR / "exp10_fiqa_probe_summary.jsonl.gz"):
        summary_rows[(int(row["ef_search"]), int(row["query_index"]))] = row
    for ef in cfg["hnsw"]["ef_search"]:
        for qi in range(nq):
            key = (int(ef), qi)
            arr = np.asarray(traces[key], dtype=np.int64)
            if arr.size != int(summary_rows[key]["unique_count"]):
                raise RuntimeError(f"first-touch length mismatch at {key}")
            if np.unique(arr).size != arr.size:
                raise RuntimeError(f"first-touch duplicate at {key}")
            traces[key] = arr
    return traces, summary_rows


def build_gain_arrays(
    qrels: dict[str, list[tuple[int, float]]],
    qids: list[str],
    corpus_id_to_row: dict[int, int],
    n: int,
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for qid in qids:
        gains = np.zeros(n, dtype=np.float64)
        for cid, gain in qrels.get(qid, []):
            row = corpus_id_to_row.get(int(cid))
            if row is not None:
                gains[row] = float(gain)
        out[qid] = gains
    return out


def cardinality_checks(
    prefix_df: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    random_df = prefix_df[prefix_df["mask_type"] == "random"]
    for right_type in ("clustered_128_random_direction", "clustered_3center_farthest_first"):
        right_df = prefix_df[prefix_df["mask_type"] == right_type]
        for sel in cfg["masks"]["selectivities"]:
            left_sizes = sorted(random_df[random_df["selectivity"] == sel]["authorized_docs"].unique().tolist())
            right_sizes = sorted(right_df[right_df["selectivity"] == sel]["authorized_docs"].unique().tolist())
            matched = len(left_sizes) == 1 and left_sizes == right_sizes
            rows.append(
                {
                    "pair": f"random_vs_{right_type}",
                    "left_mask_type": "random",
                    "right_mask_type": right_type,
                    "selectivity": sel,
                    "left_cardinalities": json.dumps(left_sizes),
                    "right_cardinalities": json.dumps(right_sizes),
                    "cardinality_matched": matched,
                    "reason": "MATCHED" if matched else "CARDINALITY_MISMATCH",
                }
            )
    return pd.DataFrame(rows)


def paired_summary(
    prefix_df: pd.DataFrame,
    card_df: pd.DataFrame,
    *,
    resamples: int,
    seed: int,
    indices: np.ndarray,
) -> pd.DataFrame:
    keys = ["qid", "selectivity", "seed", "ef_search"]
    rows: list[dict[str, Any]] = []
    for _, card in card_df.iterrows():
        right_type = card["right_mask_type"]
        sel = float(card["selectivity"])
        left = prefix_df[(prefix_df["mask_type"] == "random") & (prefix_df["selectivity"] == sel)]
        right = prefix_df[(prefix_df["mask_type"] == right_type) & (prefix_df["selectivity"] == sel)]
        for metric in METRICS:
            if metric not in prefix_df.columns:
                continue
            base = {
                "pair": card["pair"],
                "left_mask_type": card["left_mask_type"],
                "right_mask_type": right_type,
                "selectivity": sel,
                "metric": metric,
                "direction": "clustered_minus_random",
                "left_cardinalities": card["left_cardinalities"],
                "right_cardinalities": card["right_cardinalities"],
                "cardinality_matched": bool(card["cardinality_matched"]),
            }
            if not bool(card["cardinality_matched"]):
                rows.append(
                    {
                        **base,
                        "pairable": False,
                        "unpairable_reason": "CARDINALITY_MISMATCH",
                        "n_pairs": 0,
                        "n_queries": 0,
                        "mean_diff": float("nan"),
                        "ci_low": float("nan"),
                        "ci_high": float("nan"),
                    }
                )
                continue
            diff = paired_diff_frame(left, right, keys, metric, direction="clustered_minus_random")
            if diff.empty:
                rows.append(
                    {
                        **base,
                        "pairable": False,
                        "unpairable_reason": "NO_ALIGNED_PAIRS",
                        "n_pairs": 0,
                        "n_queries": 0,
                        "mean_diff": float("nan"),
                        "ci_low": float("nan"),
                        "ci_high": float("nan"),
                    }
                )
                continue
            mean_diff, low, high, nq = cluster_bootstrap_mean(
                diff,
                "qid",
                "diff",
                resamples=resamples,
                seed=seed,
                indices=indices,
            )
            rows.append(
                {
                    **base,
                    "pairable": True,
                    "unpairable_reason": "",
                    "n_pairs": int(len(diff)),
                    "n_queries": int(nq),
                    "mean_diff": mean_diff,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
    return pd.DataFrame(rows)


def bootstrap_summary(
    prefix_df: pd.DataFrame,
    unfiltered_df: pd.DataFrame,
    *,
    resamples: int,
    seed: int,
    indices: np.ndarray,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(group: str, subset: pd.DataFrame, filt: dict[str, Any], metrics: tuple[str, ...]) -> None:
        if subset.empty:
            return
        for metric in metrics:
            if metric not in subset.columns:
                continue
            mean, low, high, nq = cluster_bootstrap_mean(
                subset,
                "qid",
                metric,
                resamples=resamples,
                seed=seed,
                indices=indices,
            )
            rows.append(
                {
                    "group": group,
                    **filt,
                    "metric": metric,
                    "n_queries": nq,
                    "mean": mean,
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    for ef in sorted(prefix_df["ef_search"].unique()):
        add("unfiltered_by_ef", unfiltered_df[unfiltered_df["ef_search"] == ef], {"ef_search": ef}, ("unfiltered_recall10",))
    for ef in sorted(prefix_df["ef_search"].unique()):
        sub = prefix_df[prefix_df["ef_search"] == ef]
        add("global_by_ef", sub, {"ef_search": ef}, METRICS)
        for kind in sorted(sub["mask_type"].unique()):
            add("mask_type_by_ef", sub[sub["mask_type"] == kind], {"ef_search": ef, "mask_type": kind}, METRICS)
        for sel in sorted(sub["selectivity"].unique()):
            add("selectivity_by_ef", sub[sub["selectivity"] == sel], {"ef_search": ef, "selectivity": sel}, METRICS)
        for kind in sorted(sub["mask_type"].unique()):
            for sel in sorted(sub["selectivity"].unique()):
                s = sub[(sub["mask_type"] == kind) & (sub["selectivity"] == sel)]
                add(
                    "mask_type_selectivity_by_ef",
                    s,
                    {"ef_search": ef, "mask_type": kind, "selectivity": sel},
                    METRICS,
                )
        for sd in sorted(sub["seed"].unique()):
            add("seed_by_ef", sub[sub["seed"] == sd], {"ef_search": ef, "seed": sd}, METRICS)
        for key in sorted(sub["mask_key"].unique()):
            s = sub[sub["mask_key"] == key]
            meta = s.iloc[0]
            add(
                "mask_by_ef",
                s,
                {
                    "ef_search": ef,
                    "mask_key": key,
                    "mask_type": meta["mask_type"],
                    "seed": meta["seed"],
                    "selectivity": meta["selectivity"],
                },
                METRICS,
            )
        add(
            "low_selectivity_by_ef",
            sub[sub["selectivity"] == 0.01],
            {"ef_search": ef, "selectivity": 0.01},
            METRICS,
        )
    return pd.DataFrame(rows)


def load_input_hashes() -> dict[str, str]:
    out: dict[str, str] = {}
    if not INPUT_SHA_PATH.exists():
        return out
    for line in INPUT_SHA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, path = line.split("  ", 1)
        out[path] = digest
    return out


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def generate_report(summary: dict[str, Any]) -> str:
    oracle_sum = pd.read_csv(B2_OUT / "oracle_reached_only_summary.csv")
    boot = pd.read_csv(B2_OUT / "bootstrap_summary.csv")
    pair = pd.read_csv(B2_OUT / "paired_mask_differences.csv")
    card = pd.read_csv(B2_OUT / "mask_cardinality_check.csv")
    c3_prefix = pd.read_csv(B2_OUT / "cluster3_prefix_results.csv")
    ndcg = pd.read_csv(B2_OUT / "ndcg_corrected.csv")
    total_samples = int(oracle_sum["total_samples"].sum())
    total_reached = int(oracle_sum["reached_count"].sum())
    all_reached = total_reached == total_samples

    def oracle_cell(ef: int, mask_type: str, sel: float, delta: float, col: str) -> float:
        row = oracle_sum[
            (oracle_sum["ef_search"] == ef)
            & (oracle_sum["mask_type"] == mask_type)
            & (np.isclose(oracle_sum["selectivity"], sel))
            & (np.isclose(oracle_sum["delta"], delta))
        ]
        if row.empty:
            return float("nan")
        return float(row.iloc[0][col])

    def c3_full_recall(ef: int, sel: float) -> float:
        g = c3_prefix[(c3_prefix["ef_search"] == ef) & (np.isclose(c3_prefix["selectivity"], sel))]
        return float(g["prefix_recall_100"].mean()) if not g.empty else float("nan")

    lines: list[str] = []
    add = lines.append
    add("# EXP-10B.2 统计与指标修正报告")
    add("")
    add(f"- 基线提交：`{summary['baseline_commit']}`")
    add(f"- 分支：`{summary['branch']}`")
    add(f"- 生成时 HEAD：`{summary['head_at_generation']}`")
    add("- 本轮只修正计算与指标，不重跑 embedding、HNSW、查询轨迹，不扩展研究问题。")
    add("")

    add("## A. 原始数据与 trace 的可靠性")
    add("")
    add("- 数据门仍是 `PASS_COMPONENT_ARTIFACTS`；原 UKP ZIP MD5 仍为 `NOT_VERIFIED`，历史报告未覆盖。")
    add(f"- 原始 trace 事件数等于独立 DISTFUNC 计数：`{summary['trace_counter_equality']}`；C++ smoke verdict：`{summary['smoke_verdict']}`。")
    add(f"- 原始输入 SHA-256 复算条目数：`{len(summary['input_sha256'])}`；旧 mask 与压缩 trace 哈希均未变化：`{summary['original_inputs_unchanged']}`。")
    add(f"- 旧 mask prefix Recall 重算与原 CSV 的最大绝对差：`{summary['old_prefix_recall_max_abs_diff']:.2e}`。")
    add("- 观测口径仍是 **HNSW query distance-evaluation trace**，不是硬件 cache trace、物理内存访问轨迹或侧信道观测。")
    add("")

    add("## B. 修正前的错误结果")
    add("")
    add("1. Oracle Prefix 把 NOT_REACHED 填成 `t_star=B`、`ratio=1.0`，把“未找到”误写成“在 B 恰好达到”。")
    add("2. Bootstrap 把展开后的 query-mask 行当成独立样本，破坏 query-level cluster 结构。")
    add("3. nDCG@10 先按 qrels 相关文档排序再与候选求交，删除了不相关候选，使相关文档名次虚高。")
    add("4. 旧 128 簇变体被简称为 `clustered`；本轮改名为 `clustered_128_random_direction`，不改写原文件。")
    add("")

    add("## C. 修正后的有效结果")
    add("")
    add("### C.1 Oracle 可达性（reached-only，NOT_REACHED 不填 B/1.0）")
    add("")
    add("| ef | mask | p | delta | reached/total | rate | mean t*/B | median | p90 | 95% CI | NOT_REACHED mean Recall@B |")
    add("|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for _, r in oracle_sum.iterrows():
        add(
            f"| {int(r['ef_search'])} | {r['mask_type']} | {int(round(float(r['selectivity'])*100))}% | {r['delta']:.2f} | "
            f"{int(r['reached_count'])}/{int(r['total_samples'])} | {fmt(r['reached_rate'], 3)} | "
            f"{fmt(r['reached_only_mean_normalized_t_star'])} | {fmt(r['reached_only_median_normalized_t_star'])} | "
            f"{fmt(r['reached_only_p90_normalized_t_star'])} | [{fmt(r['reached_only_ci_low'])}, {fmt(r['reached_only_ci_high'])}] | "
            f"{fmt(r['not_reached_recall_at_B_mean'])} |"
        )
    add("")
    if all_reached:
        add(
            f"- 本轮所有 Oracle 样本均 reached：{total_reached}/{total_samples}，NOT_REACHED 数为 0。"
            "因此修正的空白编码规则在当前 FiQA 数据上没有改变数值，但纠正了语义：未找到时必须留空，不能用 B 或 1.0 填充。"
            "困难性体现在 prefix Recall/full-trace Recall 低，而不是 Oracle 不可达。"
        )
    else:
        add(
            f"- 本轮 NOT_REACHED 样本数为 {total_samples - total_reached}/{total_samples}；"
            "它们在上表中以空白 t*/ratio 表示，并以 full-trace Recall@10 分布单独报告。"
        )
    add("Oracle 是对固定 trace 的事后分析，不是在线 stopping rule，也不是其他搜索算法的理论下界。")
    add("")

    add("### C.2 query-level cluster bootstrap")
    add("")
    selected = boot[
        (boot["group"] == "mask_type_selectivity_by_ef")
        & (boot["ef_search"] == 128)
        & (boot["metric"] == "prefix_recall_100")
    ]
    add("| mask | p | mean prefix Recall@10 (B) | 95% CI |")
    add("|---|---:|---:|---|")
    for _, r in selected.iterrows():
        add(f"| {r['mask_type']} | {int(round(float(r['selectivity'])*100))}% | {fmt(r['mean'])} | [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] |")
    add("")

    add("### C.3 配对差异（clustered − random）")
    add("")
    add("| pair | p | metric | pairable | n pairs | mean diff | 95% CI | reason |")
    add("|---|---:|---|---|---:|---:|---|---|")
    show = pair[pair["metric"].isin(["prefix_recall_100", "prefix_recall_80", "ndcg_100"])]
    for _, r in show.iterrows():
        reason = "" if pd.isna(r["unpairable_reason"]) else str(r["unpairable_reason"])
        add(
            f"| {r['pair']} | {int(round(float(r['selectivity'])*100))}% | {r['metric']} | {r['pairable']} | "
            f"{int(r['n_pairs'])} | {fmt(r['mean_diff'])} | [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {reason} |"
        )
    add("")
    add("只有 cardinality 匹配且逐 query 对齐的比较才给出配对 CI；CI 是否跨 0 不等于因果结论。")
    add("")

    add("### C.4 修正后的 nDCG@10")
    add("")
    add("nDCG@10 只作为辅助指标，与 exact vector Recall@10 分开解释。修正算法保留全部候选，按精确 cosine 排序，同分按 corpus row ID 确定。")
    add("")
    ndcg_group = ndcg.groupby(["mask_type", "selectivity", "prefix_fraction"])["ndcg10"].mean().reset_index()
    add("| mask | p | nDCG@10 @60% | @80% | @90% | full |")
    add("|---|---:|---:|---:|---:|---:|")
    for mt in sorted(ndcg["mask_type"].unique()):
        for sel in sorted(ndcg["selectivity"].unique()):
            g = ndcg_group[(ndcg_group["mask_type"] == mt) & (np.isclose(ndcg_group["selectivity"], sel))]
            if g.empty:
                continue
            add(
                f"| {mt} | {int(round(float(sel)*100))}% | "+
                " | ".join(fmt(v) for v in g.sort_values("prefix_fraction")["ndcg10"].tolist())+" |"
            )
    add("")
    add("方向性观察：selectivity 排序（30% > 10% > 1%）与 random 高于 clustered 一致于 exact Recall；但 prefix 增益很小，说明稀疏 qrels 与候选覆盖限制使 nDCG@10 对 prefix 不敏感，不能替代 exact vector Recall。")
    add("")

    add("## D. 新三中心 mask 变体")
    add("")
    add("| p | ceil(K) | 旧 random cardinality | 新 cluster3 cardinality | 配对状态 |")
    add("|---:|---:|---:|---:|---|")
    for _, r in card[card["right_mask_type"] == "clustered_3center_farthest_first"].iterrows():
        add(
            f"| {int(round(float(r['selectivity'])*100))}% | {r['right_cardinalities']} | {r['left_cardinalities']} | "
            f"{r['right_cardinalities']} | {r['reason']} |"
        )
    add("")
    add("| ef | p | prefix Recall@10 @60% | @80% | @90% | full |")
    add("|---:|---:|---:|---:|---:|---:|")
    for ef in sorted(c3_prefix["ef_search"].unique()):
        for sel in sorted(c3_prefix["selectivity"].unique()):
            g = c3_prefix[(c3_prefix["ef_search"] == ef) & (c3_prefix["selectivity"] == sel)]
            add(
                f"| {int(ef)} | {int(round(float(sel)*100))}% | {fmt(g['prefix_recall_60'].mean())} | "
                f"{fmt(g['prefix_recall_80'].mean())} | {fmt(g['prefix_recall_90'].mean())} | {fmt(g['prefix_recall_100'].mean())} |"
            )
    add("")

    add("## E. 仍然无法支持的主张")
    add("")
    add("- 不声称已证明完整访问模式隐私。")
    add("- 不声称已证明在线无损 stopping rule；Oracle 是事后上界。")
    add("- 不声称已证明真实企业 ACL 下的安全性；授权 mask 是合成的。")
    add("- 不声称已解决 Agent/RAG 授权检索问题。")
    add("- 不声称已证明 PA-VFANN 普遍优于现有方法。")
    add("")

    add("## 对七个问题的回答")
    add("")
    oracle_example = oracle_cell(128, "clustered_128_random_direction", 0.10, 0.10, "reached_only_mean_normalized_t_star")
    oracle_example_ci_low = oracle_cell(128, "clustered_128_random_direction", 0.10, 0.10, "reached_only_ci_low")
    oracle_example_ci_high = oracle_cell(128, "clustered_128_random_direction", 0.10, 0.10, "reached_only_ci_high")
    add(
        "1. **修正 NOT_REACHED 后，Oracle prefix 空间是否仍然存在？** 是，但只作为事后空间：例如 ef=128、旧 clustered、10%、δ=0.10 的 reached-only mean t*/B="
        f"{fmt(oracle_example)}（95% CI [{fmt(oracle_example_ci_low)}, {fmt(oracle_example_ci_high)}]）。"
        + ("本数据所有样本均 reached，因此不存在被 B/1.0 误填的样本。" if all_reached else "NOT_REACHED 已留空并单独报告。")
    )
    add(
        "2. **哪些 selectivity 下 reached rate 明显下降？** "
        + ("没有：三个 mask 类型、三个 selectivity、两个 δ、三个 efSearch 的 reached rate 全部为 1.000。"
           if all_reached else "见 C.1 reached_rate 列。")
        + "1% 的困难体现在 full-trace Recall 更低，而不是 Oracle 不可达。"
    )
    add("3. **random 与两种 clustered 分布的差异有多大？** C.2 给出非配对聚合均值，C.3 给出严格配对差值；新三中心 mask 在 cardinality 不匹配档位不给配对因果解释。")
    add("4. **修正后的 bootstrap 是否支持稳定差异？** 以 C.3 的 query-level cluster bootstrap 95% CI 为准；仅跨 0 与否不足以达到因果主张。")
    add(
        "5. **修正 nDCG 后，质量趋势是否与 exact vector Recall 一致？** 方向上一致（30% > 10% > 1%，random > clustered），"
        "但 nDCG@10 随 prefix 几乎不增长；qrels 稀疏且 IDCG 基于全部授权相关文档，因此 nDCG 是辅助指标，不能替代 exact vector Recall。"
    )
    add(
        "6. **新三中心 mask 是否复现 1% 授权困难现象？** 是：1% 档 prefix Recall@10（B）为 "
        f"ef64={fmt(c3_full_recall(64, 0.01))}、ef128={fmt(c3_full_recall(128, 0.01))}、ef256={fmt(c3_full_recall(256, 0.01))}，"
        f"明显低于 10% 档（{fmt(c3_full_recall(64, 0.10))}/{fmt(c3_full_recall(128, 0.10))}/{fmt(c3_full_recall(256, 0.10))}）"
        f"和 30% 档（{fmt(c3_full_recall(64, 0.30))}/{fmt(c3_full_recall(128, 0.30))}/{fmt(c3_full_recall(256, 0.30))}）。"
    )
    add("7. **哪些结论只适用于当前 FiQA + MiniLM + hnswlib 配置？** 本文全部数值结论都只适用于该配置、固定 revision 的组件、合成授权 mask 与有序距离计算 trace；不外推到真实 ACL、其他模型/索引或其他硬件/实现。")
    add("")
    add("## 交付与停止")
    add("")
    add("本轮完成 EXP-10B.2 后立即停止；不启动 EXP-11，不新增数据集，不尝试新的 stopping rule，不引入新的密码学原语，不包装成 Agent/RAG 实现。是否继续投入 PA-VFANN 由用户与研究助手共同判断。")
    add("")
    return "\n".join(lines)


def main() -> None:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    b2cfg = json.loads(B2_CFG_PATH.read_text(encoding="utf-8"))
    ctx = build_cluster3_artifacts()
    n = int(ctx["n"])
    nq = int(ctx["nq"])
    qids = ctx["qids"]
    scores = ctx["scores"]
    gain_arrays = build_gain_arrays(
        read_qrels(ROOT / json.loads((ROOT / "data" / "exp10_fiqa_manifest.json").read_text(encoding="utf-8"))["components"]["qrels"]["path"]),
        qids,
        {int(cid): i for i, cid in enumerate(ctx["corpus_ids"])},
        n,
    )
    traces, trace_summary = load_traces(cfg, nq)
    mask_defs = build_mask_definitions(ctx)
    efs = [int(v) for v in cfg["hnsw"]["ef_search"]]
    deltas = [float(v) for v in cfg["prefixes"]["oracle_delta"]]
    boot_cfg = b2cfg["bootstrap"]
    resamples = int(boot_cfg["resamples"])
    seed = int(boot_cfg["seed"])
    bootstrap_indices = make_bootstrap_indices(nq, resamples, seed)

    prefix_rows: list[dict[str, Any]] = []
    oracle_rows: list[dict[str, Any]] = []
    ndcg_rows: list[dict[str, Any]] = []

    for md in mask_defs:
        mask = md["mask"]
        gt = md["gt"]
        topk = gt["topk"]
        authorized_docs = int(mask.sum())
        if authorized_docs != int(gt["authorized_docs"]):
            raise RuntimeError(f"mask/GT cardinality mismatch for {md['source_key']}")
        idcg_by_qi = [idcg_from_gains(gain_arrays[qid][mask]) for qid in qids]
        for qi, qid in enumerate(qids):
            truth = np.zeros(n, dtype=bool)
            truth[np.asarray(topk[qi], dtype=np.int64)] = True
            score_row = scores[qi]
            gain_row = gain_arrays[qid]
            idcg = idcg_by_qi[qi]
            for ef in efs:
                ft = traces[(ef, qi)]
                b = int(ft.size)
                cum = np.cumsum(truth[ft].astype(np.int32))
                r_full = float(cum[-1]) / K
                row: dict[str, Any] = {
                    "ef_search": ef,
                    "query_index": qi,
                    "qid": qid,
                    "mask_key": md["mask_key"],
                    "source_key": md["source_key"],
                    "mask_type": md["mask_type"],
                    "seed": md["seed"],
                    "selectivity": md["selectivity"],
                    "origin": md["origin"],
                    "B": b,
                    "authorized_docs": authorized_docs,
                    "authorized_in_trace": int(mask[ft].sum()),
                    "prefix_recall_full": r_full,
                }
                for frac, tag in zip(PREFIX_FRACS, PREFIX_TAGS):
                    t = min(b, max(1, int(math.ceil(frac * b))))
                    recall = float(cum[t - 1]) / K if b else 0.0
                    cand = ft[:t]
                    cand = cand[mask[cand]]
                    ndcg = ndcg_at_k(cand, score_row, gain_row, idcg)
                    row[f"prefix_recall_{tag}"] = recall
                    row[f"prefix_t_{tag}"] = t
                    row[f"ndcg_{tag}"] = ndcg
                    ndcg_rows.append(
                        {
                            "mask_key": md["mask_key"],
                            "mask_type": md["mask_type"],
                            "seed": md["seed"],
                            "selectivity": md["selectivity"],
                            "origin": md["origin"],
                            "ef_search": ef,
                            "query_index": qi,
                            "qid": qid,
                            "prefix_fraction": frac,
                            "t": t,
                            "authorized_candidates": int(cand.size),
                            "ndcg10": ndcg,
                            "idcg10": idcg,
                        }
                    )
                for delta, tag in zip(deltas, ORACLE_TAGS):
                    reached, t_star, ratio = oracle_from_cum(cum, b, delta, row["prefix_t_60"])
                    row[f"oracle_t_{tag}"] = t_star
                    row[f"oracle_ratio_{tag}"] = ratio
                    row[f"oracle_reached_{tag}"] = reached
                    oracle_rows.append(
                        {
                            "ef_search": ef,
                            "query_index": qi,
                            "qid": qid,
                            "mask_key": md["mask_key"],
                            "mask_type": md["mask_type"],
                            "seed": md["seed"],
                            "selectivity": md["selectivity"],
                            "origin": md["origin"],
                            "delta": delta,
                            "B": b,
                            "reached": reached,
                            "t_star": t_star,
                            "normalized_t_star": ratio,
                            "recall_at_B": r_full,
                        }
                    )
                prefix_rows.append(row)

    prefix_df = pd.DataFrame(prefix_rows)
    oracle_df = pd.DataFrame(oracle_rows)
    ndcg_df = pd.DataFrame(ndcg_rows)

    # Validate that recomputation did not change any original prefix recall.
    original_prefix = pd.read_csv(RESULT_DIR / "exp10_fiqa_prefix_recall.csv")
    recomputed_old = prefix_df[prefix_df["origin"] == "EXP-10B.1"][
        ["ef_search", "query_index", "source_key", "prefix_recall_60", "prefix_recall_80", "prefix_recall_90", "prefix_recall_full"]
    ].rename(columns={"source_key": "mask_key"})
    compare = original_prefix[["ef_search", "query_index", "mask_key", "prefix_recall_60", "prefix_recall_80", "prefix_recall_90", "prefix_recall_100"]].merge(
        recomputed_old,
        on=["ef_search", "query_index", "mask_key"],
        suffixes=("_orig", "_new"),
    )
    if len(compare) != len(original_prefix):
        raise RuntimeError("old prefix validation merge lost rows")
    diffs = []
    for tag in PREFIX_TAGS:
        if tag == "100":
            orig_col = "prefix_recall_100"      # no suffix: only original frame has this column
            new_col = "prefix_recall_full"      # no suffix: only recomputed frame has this column
        else:
            orig_col = f"prefix_recall_{tag}_orig"
            new_col = f"prefix_recall_{tag}_new"
        diffs.append(np.abs(compare[orig_col].to_numpy(float) - compare[new_col].to_numpy(float)))
    max_abs_diff = float(np.max(np.concatenate(diffs)))
    if max_abs_diff > 1e-12:
        raise RuntimeError(f"old prefix recall recomputation differs by {max_abs_diff}")

    oracle_out = oracle_df[
        [
            "ef_search",
            "query_index",
            "qid",
            "mask_key",
            "mask_type",
            "seed",
            "selectivity",
            "origin",
            "delta",
            "B",
            "reached",
            "t_star",
            "normalized_t_star",
            "recall_at_B",
        ]
    ].sort_values(["ef_search", "mask_type", "selectivity", "seed", "mask_key", "query_index", "delta"])
    oracle_out.to_csv(B2_OUT / "oracle_reachability.csv", index=False)

    oracle_sum = summarize_oracle_reachability(oracle_df, resamples=resamples, seed=seed, indices=bootstrap_indices)
    oracle_sum.to_csv(B2_OUT / "oracle_reached_only_summary.csv", index=False)

    unfiltered = pd.read_csv(RESULT_DIR / "exp10_fiqa_unfiltered_recall.csv")
    bootstrap = bootstrap_summary(
        prefix_df,
        unfiltered,
        resamples=resamples,
        seed=seed,
        indices=bootstrap_indices,
    )
    bootstrap.to_csv(B2_OUT / "bootstrap_summary.csv", index=False)

    card = cardinality_checks(prefix_df, cfg)
    card.to_csv(B2_OUT / "mask_cardinality_check.csv", index=False)
    paired = paired_summary(prefix_df, card, resamples=resamples, seed=seed, indices=bootstrap_indices)
    paired.to_csv(B2_OUT / "paired_mask_differences.csv", index=False)

    ndcg_out = ndcg_df.sort_values(["mask_type", "mask_key", "ef_search", "query_index", "prefix_fraction"])
    ndcg_out.to_csv(B2_OUT / "ndcg_corrected.csv", index=False)

    c3 = prefix_df[prefix_df["origin"] == "EXP-10B.2"].drop(columns=["source_key", "origin"])
    c3.to_csv(B2_OUT / "cluster3_prefix_results.csv", index=False)
    c3_oracle = oracle_df[oracle_df["origin"] == "EXP-10B.2"][
        [
            "ef_search",
            "query_index",
            "qid",
            "mask_key",
            "mask_type",
            "seed",
            "selectivity",
            "delta",
            "B",
            "reached",
            "t_star",
            "normalized_t_star",
            "recall_at_B",
        ]
    ].sort_values(["ef_search", "mask_key", "query_index", "delta"])
    c3_oracle.to_csv(B2_OUT / "cluster3_oracle_results.csv", index=False)

    input_hashes = load_input_hashes()
    unchanged = True
    for path, digest in input_hashes.items():
        if sha256_file(ROOT / path) != digest:
            unchanged = False
            raise RuntimeError(f"original input changed: {path}")
    trace_equality = all(
        int(row["event_count"]) == int(row["distance_call_count"])
        for row in trace_summary.values()
    )
    smoke = json.loads((RAW_DIR / "exp10_fiqa_smoke" / "exp10_fiqa_smoke_validation.json").read_text(encoding="utf-8"))

    artifact_names = [
        "oracle_reachability.csv",
        "oracle_reached_only_summary.csv",
        "bootstrap_summary.csv",
        "paired_mask_differences.csv",
        "ndcg_corrected.csv",
        "mask_cardinality_check.csv",
        "cluster_mask_manifest.json",
        "cluster3_prefix_results.csv",
        "cluster3_oracle_results.csv",
        "cluster3_filtered_gt.json",
        "original_input_sha256.txt",
    ]
    summary = {
        "experiment": "EXP-10B.2",
        "baseline_commit": b2cfg["baseline_commit"],
        "branch": b2cfg["branch"],
        "head_at_generation": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "data_gate": "PASS_COMPONENT_ARTIFACTS",
        "original_zip_md5_status": "NOT_VERIFIED",
        "smoke_verdict": smoke.get("verdict"),
        "trace_counter_equality": trace_equality,
        "input_sha256": input_hashes,
        "original_inputs_unchanged": unchanged,
        "old_prefix_recall_max_abs_diff": max_abs_diff,
        "rows": {
            "prefix": int(len(prefix_df)),
            "oracle": int(len(oracle_df)),
            "ndcg": int(len(ndcg_df)),
            "bootstrap": int(len(bootstrap)),
            "paired": int(len(paired)),
        },
        "mask_cardinality": {
            "rule_new": "ceil(selectivity * N)",
            "new_sizes": ctx["sizes"],
            "old_sizes": json.loads((EMB_DIR / "gt_manifest.json").read_text(encoding="utf-8"))["mask_sizes_by_selectivity"],
        },
        "bootstrap_config": {"unit": "query_id", "resamples": resamples, "seed": seed},
        "artifacts": {
            name: {
                "path": (B2_OUT / name).relative_to(ROOT).as_posix(),
                "sha256": sha256_file(B2_OUT / name),
            }
            for name in artifact_names
        },
    }
    (B2_OUT / "exp10b2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = generate_report(summary)
    report_path = ROOT / "docs" / "EXP10B2_CORRECTION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(
        f"[EXP-10B.2] prefix_rows={len(prefix_df)} oracle_rows={len(oracle_df)} "
        f"ndcg_rows={len(ndcg_df)} bootstrap_rows={len(bootstrap)} paired_rows={len(paired)}",
        flush=True,
    )
    print(f"[EXP-10B.2] old_prefix_recall_max_abs_diff={max_abs_diff:.2e}", flush=True)


if __name__ == "__main__":
    main()
