"""H1.2: independent-ACL generalization of the E1 stop-boundary leakage.

Fixed retrieval environment (vectors, queries, graph, public plans) is built
once from the frozen EXP-01 config. Only the ACL random stream changes: each
ACL instance is generated from a copy of the Dataset with a new master_seed
while reusing the exact same vector and query array objects.

Three logical boundaries are kept separate:
  * simulate_e1_stop    -- trusted execution side, consumes the ACL;
  * infer_last_node     -- attack side, imported from H1.1, receives no ACL;
  * evaluate_inference  -- independent scorer, consumes the ACL only after the
                           attack has produced its output.

No new attack, no E2 path, no HNSW/FiQA, no defense, no extra ACL samples.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from pa_vfann.config import Config, default_config_path, load_config  # noqa: E402
from pa_vfann.dataset import Dataset  # noqa: E402
from pa_vfann.policies import DIST_CODE, build_policy  # noqa: E402
from pa_vfann.search_common import plan_fixed_trace  # noqa: E402

from experiments.analyze_e1_stop_leakage import infer_last_node  # noqa: E402
from experiments.exp_common import prepare  # noqa: E402

MIN_VISITS = 20
MAX_BUDGET = 1000
TOP_K = 10
ACL_INSTANCES_PER_CELL = 30
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20261125
ACL_SEED_NAMESPACE = 0x4831323032  # fixed namespace: H120

ACL_COLUMNS = [
    "acl_id", "policy_type", "selectivity_pct", "acl_seed", "mask_sha256",
    "authorized_docs", "actual_selectivity", "sigma", "n_centers",
    "center_ids", "total_queries", "informative_queries", "tau_eq_m",
    "tau_eq_B", "unique_inferred_nodes", "correct_events",
    "precision", "informative_rate", "acl_coverage", "unique_yield",
    "duplicate_events", "duplicate_event_rate", "tau_p05", "tau_p25",
    "tau_p50", "tau_p75", "tau_p95", "lemma_ok_events",
]

SUMMARY_COLUMNS = [
    "policy_type", "selectivity_pct", "acl_instances",
    "mean_coverage", "coverage_ci_low", "coverage_ci_high",
    "mean_informative_rate", "informative_rate_ci_low",
    "informative_rate_ci_high", "mean_unique_yield", "unique_yield_ci_low",
    "unique_yield_ci_high", "mean_duplicate_event_rate",
    "precision_invariant", "bootstrap_reps",
]


# --------------------------------------------------------------------------- #
# Deterministic ACL streams and content hashes                                 #
# --------------------------------------------------------------------------- #
def derive_acl_seeds(
    data_seed: int,
    policy_type: str,
    selectivity_pct: int,
    count: int = ACL_INSTANCES_PER_CELL,
) -> list[int]:
    """Return independent, reproducible ACL seeds for one cell."""
    if policy_type not in DIST_CODE:
        raise ValueError(f"unknown policy distribution: {policy_type}")
    if int(count) <= 0:
        raise ValueError("count must be positive")
    seq = np.random.SeedSequence(
        [
            int(data_seed),
            DIST_CODE[policy_type],
            int(round(float(selectivity_pct))),
            ACL_SEED_NAMESPACE,
        ]
    )
    children = seq.spawn(int(count))
    return [int(child.generate_state(1, dtype=np.uint64)[0]) for child in children]


def cell_bootstrap_seed(policy_type: str, selectivity_pct: int) -> int:
    if policy_type not in DIST_CODE:
        raise ValueError(f"unknown policy distribution: {policy_type}")
    seq = np.random.SeedSequence(
        [
            int(BOOTSTRAP_SEED),
            DIST_CODE[policy_type],
            int(round(float(selectivity_pct))),
            0x42535452,  # fixed namespace: BSTR
        ]
    )
    return int(seq.generate_state(1, dtype=np.uint64)[0])


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def mask_sha256(mask: Sequence[bool]) -> str:
    packed = np.packbits(np.asarray(mask, dtype=np.uint8))
    return hashlib.sha256(packed.tobytes()).hexdigest()


def graph_sha256(graph: object) -> str:
    digest = hashlib.sha256()
    header = (
        f"degree={int(graph.degree)}|symm={int(bool(graph.symm))}|"
        f"components={int(graph.connected_components)}|"
        f"max_degree={int(graph.max_undirected_degree)}|"
        f"construction={graph.construction}\n"
    )
    digest.update(header.encode("utf-8"))
    for label, adjacency in (
        ("adjacency", graph.adjacency),
        ("forward", graph.forward_adjacency),
    ):
        digest.update(label.encode("ascii") + b"\n")
        for row in adjacency:
            digest.update(",".join(str(int(v)) for v in row).encode("ascii") + b"\n")
    return digest.hexdigest()


def public_paths_sha256(paths: Sequence[Sequence[int]]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(",".join(str(int(v)) for v in path).encode("ascii") + b"\n")
    return digest.hexdigest()


def path_trace_sha16(path: Sequence[int]) -> str:
    return hashlib.sha256(
        ",".join(str(int(v)) for v in path).encode("ascii")
    ).hexdigest()[:16]


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# ACL construction and the three separated roles                               #
# --------------------------------------------------------------------------- #
def make_acl_dataset_and_policy(
    base_dataset: Dataset,
    policy_type: str,
    selectivity: float,
    sigma: float,
    n_centers: int,
    acl_seed: int,
) -> tuple[Dataset, object]:
    """Change only the ACL stream; vectors and queries remain the same objects."""
    acl_dataset = replace(base_dataset, master_seed=int(acl_seed))
    if acl_dataset.vectors is not base_dataset.vectors:
        raise RuntimeError("ACL dataset replaced the vector array object")
    if acl_dataset.query_vectors is not base_dataset.query_vectors:
        raise RuntimeError("ACL dataset replaced the query array object")
    policy = build_policy(
        acl_dataset, policy_type, float(selectivity), float(sigma), int(n_centers)
    )
    return acl_dataset, policy


def simulate_e1_stop(
    public_path: Sequence[int],
    mask: Sequence[bool],
    k: int = TOP_K,
    min_visits: int = MIN_VISITS,
    max_budget: int = MAX_BUDGET,
) -> int:
    """Trusted execution side: recreate E1's policy-dependent stop position."""
    k = int(k)
    budget = int(max_budget)
    if k <= 0 or budget <= 0:
        raise ValueError("k and max_budget must be positive")
    floor = min(int(min_visits), budget)
    if floor <= 0:
        raise ValueError("min_visits must be positive")
    legal = 0
    for position, node in enumerate(public_path, start=1):
        if mask[int(node)]:
            legal += 1
        if position >= floor and legal >= k:
            return position
    return min(len(public_path), budget)


def evaluate_inference(
    public_path: Sequence[int],
    tau: int,
    mask: Sequence[bool],
    inferred: int | None,
    k: int = TOP_K,
) -> dict[str, object]:
    """Independent scorer: use the ACL only after the attack has answered."""
    if inferred is None:
        return {"inferred_authorized": None, "prefix_count": None, "lemma_holds": None}
    inferred_authorized = bool(mask[int(inferred)])
    prefix_count = sum(1 for v in public_path[: int(tau) - 1] if mask[int(v)])
    return {
        "inferred_authorized": inferred_authorized,
        "prefix_count": prefix_count,
        "lemma_holds": bool(inferred_authorized and prefix_count == int(k) - 1),
    }


def compute_acl_metrics(
    taus: Sequence[int],
    inferred_nodes: Sequence[int],
    authorized_count: int,
    n_queries: int,
    correct_events: int,
    min_visits: int = MIN_VISITS,
    max_budget: int = MAX_BUDGET,
) -> dict[str, object]:
    """Per-ACL descriptive metrics with U <= min(M, I) as a hard invariant."""
    tau_list = [int(v) for v in taus]
    nodes = [int(v) for v in inferred_nodes]
    i = len(tau_list)
    if len(nodes) != i:
        raise ValueError("one inferred node is required per informative event")
    if any(v <= min_visits or v >= max_budget for v in tau_list):
        raise ValueError("taus must be strictly inside (min_visits, max_budget)")
    m = int(authorized_count)
    if m <= 0:
        raise ValueError("authorized_count must be positive")
    u = len(set(nodes))
    if u > min(m, i):
        raise ValueError(f"metric invariant violated: U={u} > min(M={m}, I={i})")
    if int(correct_events) != i:
        raise RuntimeError("precision invariant failed: not all inferred nodes were authorized")
    if i == 0:
        q = [None] * 5
        precision: float | None = None
        duplicate_rate: float | None = 0.0
    else:
        q = [float(v) for v in np.percentile(tau_list, [5, 25, 50, 75, 95])]
        precision = float(correct_events) / float(i)
        duplicate_rate = float(i - u) / float(i)
    return {
        "informative_rate": float(i) / float(int(n_queries)),
        "acl_coverage": float(u) / float(m),
        "unique_yield": (float(u) / float(min(m, i))) if i else 0.0,
        "duplicate_events": int(i - u),
        "duplicate_event_rate": duplicate_rate,
        "tau_p05": q[0], "tau_p25": q[1], "tau_p50": q[2],
        "tau_p75": q[3], "tau_p95": q[4],
        "precision": precision,
        "unique_nodes": u,
        "informative_queries": i,
    }


# --------------------------------------------------------------------------- #
# ACL-level bootstrap                                                          #
# --------------------------------------------------------------------------- #
def bootstrap_index_matrix(n_units: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Resample ACL units, never queries: shape is (n_boot, n_units)."""
    if int(n_units) <= 0 or int(n_boot) <= 0:
        raise ValueError("n_units and n_boot must be positive")
    return rng.integers(0, int(n_units), size=(int(n_boot), int(n_units)))


def bootstrap_mean_ci(
    values: Sequence[float],
    rng: np.random.Generator,
    n_boot: int = BOOTSTRAP_REPS,
) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("values must be a non-empty one-dimensional sequence")
    index = bootstrap_index_matrix(arr.size, int(n_boot), rng)
    means = arr[index].mean(axis=1)
    return (
        float(arr.mean()),
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


# --------------------------------------------------------------------------- #
# Experiment driver                                                            #
# --------------------------------------------------------------------------- #
def run_experiment(
    config: Config | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    cfg = config if config is not None else load_config(default_config_path())
    out = Path(output_dir) if output_dir is not None else ROOT / "results" / "h1_2_acl_generalization"
    out.mkdir(parents=True, exist_ok=True)

    dataset, graph, qdist = prepare(cfg)
    n = dataset.n
    n_queries = dataset.n_queries
    k = int(cfg["search"]["top_k"])
    max_budget = max(int(v) for v in cfg["search"]["budgets"])
    min_visits = int(cfg["search"]["initial_budget"])
    sigma = float(cfg["policies"]["clustered_sigma"])
    n_centers = int(cfg["policies"]["clustered_centers"])
    data_seed = int(cfg["data"]["seed"])
    policy_types = [str(v) for v in cfg["policies"]["types"]]
    selectivities = [float(v) for v in cfg["policies"]["selectivities"]]

    if (n, n_queries, k, max_budget, min_visits) != (10000, 200, 10, 1000, 20):
        raise RuntimeError(
            "frozen H1.2 environment mismatch: expected n=10000, n_queries=200, "
            "top_k=10, max_budget=1000, min_visits=20"
        )

    print(
        f"[h1.2] fixed environment: n={n} n_queries={n_queries} "
        f"graph_components={graph.connected_components} max_budget={max_budget}",
        flush=True,
    )
    plans = [plan_fixed_trace(qdist[q], graph, max_budget) for q in range(n_queries)]
    if any(len(plan[0]) != max_budget for plan in plans):
        raise RuntimeError("public plans are not full-length fixed traces")
    trace_hashes = [path_trace_sha16(plan[0]) for plan in plans]

    environment_hashes = {
        "vectors_sha256": array_sha256(dataset.vectors),
        "queries_sha256": array_sha256(dataset.query_vectors),
        "qdist_sha256": array_sha256(qdist),
        "graph_sha256": graph_sha256(graph),
        "public_paths_sha256": public_paths_sha256([plan[0] for plan in plans]),
        "config_sha256": file_sha256(Path(cfg.path)),
    }

    acl_rows: list[dict[str, object]] = []
    cell_rows: dict[tuple[str, int], list[dict[str, object]]] = {}

    for policy_type in policy_types:
        for selectivity in selectivities:
            selectivity_pct = int(round(selectivity * 100))
            expected_m = int(round(selectivity * n))
            seeds = derive_acl_seeds(data_seed, policy_type, selectivity_pct)
            if len(set(seeds)) != len(seeds):
                raise RuntimeError(f"duplicate ACL seeds in cell {policy_type}/{selectivity_pct}")
            cell_mask_hashes: set[str] = set()

            for acl_index, acl_seed in enumerate(seeds):
                acl_id = f"{policy_type}_{selectivity_pct:02d}_{acl_index:02d}"
                _, policy = make_acl_dataset_and_policy(
                    dataset, policy_type, selectivity, sigma, n_centers, acl_seed
                )
                m = int(policy.actual_count)
                if m != expected_m:
                    raise RuntimeError(
                        f"cardinality mismatch for {acl_id}: {m} != {expected_m}"
                    )
                msha = mask_sha256(policy.mask)
                if msha in cell_mask_hashes:
                    raise RuntimeError(f"duplicate ACL mask in cell {policy_type}/{selectivity_pct}")
                cell_mask_hashes.add(msha)

                bits = [bool(v) for v in policy.mask]
                taus: list[int] = []
                inferred: list[int] = []
                correct_events = 0
                tau_eq_m = 0
                tau_eq_b = 0

                for q, plan in enumerate(plans):
                    path = plan[0]
                    tau = simulate_e1_stop(path, bits, k, min_visits, max_budget)
                    if tau == min_visits:
                        tau_eq_m += 1
                        continue
                    if tau >= max_budget:
                        tau_eq_b += 1
                        continue
                    # ATTACK: public path + tau only. No ACL is passed in.
                    node = infer_last_node(path, tau, min_visits, max_budget)
                    if node is None:
                        raise RuntimeError(f"attack returned None for informative event {acl_id}/q{q}")
                    verdict = evaluate_inference(path, tau, bits, node, k)
                    if verdict["inferred_authorized"] is not True or verdict["lemma_holds"] is not True:
                        raise RuntimeError(
                            f"deterministic lemma violation at {acl_id}/q{q}: "
                            f"tau={tau} node={node} verdict={verdict}"
                        )
                    taus.append(tau)
                    inferred.append(int(node))
                    correct_events += 1

                metrics = compute_acl_metrics(
                    taus, inferred, m, n_queries, correct_events, min_visits, max_budget
                )
                row: dict[str, object] = {
                    "acl_id": acl_id,
                    "policy_type": policy_type,
                    "selectivity_pct": selectivity_pct,
                    "acl_seed": acl_seed,
                    "mask_sha256": msha,
                    "authorized_docs": m,
                    "actual_selectivity": float(policy.actual_selectivity),
                    "sigma": sigma,
                    "n_centers": n_centers,
                    "center_ids": ",".join(str(int(v)) for v in policy.center_ids),
                    "total_queries": n_queries,
                    "informative_queries": int(metrics["informative_queries"]),
                    "tau_eq_m": tau_eq_m,
                    "tau_eq_B": tau_eq_b,
                    "unique_inferred_nodes": int(metrics["unique_nodes"]),
                    "correct_events": correct_events,
                    "precision": metrics["precision"],
                    "informative_rate": metrics["informative_rate"],
                    "acl_coverage": metrics["acl_coverage"],
                    "unique_yield": metrics["unique_yield"],
                    "duplicate_events": int(metrics["duplicate_events"]),
                    "duplicate_event_rate": metrics["duplicate_event_rate"],
                    "tau_p05": metrics["tau_p05"],
                    "tau_p25": metrics["tau_p25"],
                    "tau_p50": metrics["tau_p50"],
                    "tau_p75": metrics["tau_p75"],
                    "tau_p95": metrics["tau_p95"],
                    "lemma_ok_events": correct_events,
                }
                acl_rows.append(row)
                cell_rows.setdefault((policy_type, selectivity_pct), []).append(row)

            print(
                f"[h1.2] {policy_type}/{selectivity_pct}%: "
                f"{len(cell_mask_hashes)} distinct ACLs",
                flush=True,
            )

    acl_df = pd.DataFrame(acl_rows, columns=ACL_COLUMNS)
    acl_csv = out / "acl_metrics.csv"
    acl_df.to_csv(acl_csv, index=False)

    summary_rows: list[dict[str, object]] = []
    for policy_type in policy_types:
        for selectivity in selectivities:
            pct = int(round(selectivity * 100))
            rows = cell_rows[(policy_type, pct)]
            if len(rows) != ACL_INSTANCES_PER_CELL:
                raise RuntimeError(f"cell {policy_type}/{pct} has {len(rows)} ACLs, expected 30")
            rng = np.random.default_rng(cell_bootstrap_seed(policy_type, pct))
            cov_mean, cov_lo, cov_hi = bootstrap_mean_ci(
                [float(r["acl_coverage"]) for r in rows], rng
            )
            inf_mean, inf_lo, inf_hi = bootstrap_mean_ci(
                [float(r["informative_rate"]) for r in rows], rng
            )
            yield_mean, yield_lo, yield_hi = bootstrap_mean_ci(
                [float(r["unique_yield"]) for r in rows], rng
            )
            precisions = [r["precision"] for r in rows]
            if any(v is not None and float(v) != 1.0 for v in precisions):
                raise RuntimeError("precision invariant failed in cell summary")
            summary_rows.append(
                {
                    "policy_type": policy_type,
                    "selectivity_pct": pct,
                    "acl_instances": len(rows),
                    "mean_coverage": cov_mean,
                    "coverage_ci_low": cov_lo,
                    "coverage_ci_high": cov_hi,
                    "mean_informative_rate": inf_mean,
                    "informative_rate_ci_low": inf_lo,
                    "informative_rate_ci_high": inf_hi,
                    "mean_unique_yield": yield_mean,
                    "unique_yield_ci_low": yield_lo,
                    "unique_yield_ci_high": yield_hi,
                    "mean_duplicate_event_rate": float(
                        np.mean([float(r["duplicate_event_rate"]) for r in rows])
                    ),
                    "precision_invariant": 1.0,
                    "bootstrap_reps": BOOTSTRAP_REPS,
                }
            )

    summary_df = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    summary_csv = out / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    manifest = {
        "experiment": "H1_2_INDEPENDENT_ACL_GENERALIZATION",
        "baseline_commit": git_head(),
        "config": cfg.raw,
        "environment_hashes": environment_hashes,
        "fixed_public_trace_sha16": trace_hashes,
        "fixed_parameters": {
            "n_vectors": n,
            "dimension": int(dataset.vectors.shape[1]),
            "n_queries": n_queries,
            "graph_degree": int(graph.degree),
            "top_k": k,
            "min_visits": min_visits,
            "max_budget": max_budget,
            "data_seed": data_seed,
            "clustered_sigma": sigma,
            "clustered_centers": n_centers,
            "acl_instances_per_cell": ACL_INSTANCES_PER_CELL,
            "total_acl_instances": len(acl_rows),
        },
        "acl_generation": {
            "method": "replace(Dataset, master_seed=acl_seed) -> build_policy",
            "data_arrays_unchanged": True,
            "seed_namespace": ACL_SEED_NAMESPACE,
            "cells": [
                {"policy_type": p, "selectivity_pct": int(round(s * 100))}
                for p in policy_types for s in selectivities
            ],
        },
        "bootstrap": {
            "unit": "acl_instance",
            "replications": BOOTSTRAP_REPS,
            "seed": BOOTSTRAP_SEED,
            "interval": "percentile_95",
            "query_level_bootstrap": False,
        },
        "output_files": {
            "acl_metrics.csv": {"sha256": file_sha256(acl_csv), "rows": len(acl_rows)},
            "summary.csv": {"sha256": file_sha256(summary_csv), "rows": len(summary_rows)},
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"[h1.2] wrote {len(acl_rows)} ACL rows and {len(summary_rows)} summary rows to {out}",
        flush=True,
    )
    return {
        "acl_rows": acl_rows,
        "summary_rows": summary_rows,
        "manifest": manifest,
        "paths": {"acl_metrics": acl_csv, "summary": summary_csv, "manifest": manifest_path},
    }


def main() -> None:
    result = run_experiment()
    for row in result["summary_rows"]:
        print(
            f"[h1.2] {row['policy_type']:>9}/{row['selectivity_pct']:>2}% "
            f"coverage={row['mean_coverage']:.4f} "
            f"informative={row['mean_informative_rate']:.4f} "
            f"unique_yield={row['mean_unique_yield']:.4f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
