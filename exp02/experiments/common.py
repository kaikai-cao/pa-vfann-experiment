"""Shared row schema and helpers for EXP-02 batch runners."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_vfann_exp02.algorithms import algorithm_variants, derive, run_log
from pa_vfann_exp02.config import Config, load_config
from pa_vfann_exp02.exp01_bridge import build_dataset, build_graph, build_policy
from pa_vfann_exp02.metrics import recall_at_k

FIELDS = [
    "experiment", "algorithm", "bridge_r", "policy_type", "selectivity_pct", "sigma",
    "pair_name", "policy_a", "policy_b", "budget", "query_id",
    "recall_at_10", "gt_size", "insufficient_gt",
    "distance_evaluations", "unique_discovered_nodes", "unique_visited_nodes",
    "expanded_nodes", "neighbor_checks", "candidate_count",
    "candidate_id_bytes", "candidate_meta_bytes", "candidate_vector_bytes",
    "candidate_transfer_bytes", "legal_candidates_count", "returned_count",
    "stop_position", "termination_reason", "actual_authorized_count",
    "actual_selectivity", "entry_node_id", "trace_sha16", "seed",
    "discovery_leakage", "visit_leakage", "expansion_leakage", "visit_edit_leakage",
    "stop_position_delta", "candidate_count_delta", "returned_count_delta",
    "output_id_leakage", "identical_discovery", "identical_visit", "identical_expansion",
    "discovery_sha_a", "discovery_sha_b", "returned_ids_a", "returned_ids_b",
]

COST_FIELDS = [
    "distance_evaluations", "unique_discovered_nodes", "unique_visited_nodes",
    "expanded_nodes", "neighbor_checks", "candidate_count", "candidate_transfer_bytes",
]


def exp02_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cli_config() -> tuple[Config, str]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(exp02_root() / "config" / "experiment.yaml"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    return load_config(args.config), args.output


def result_path(config: Config, explicit: str, name: str = "experiment_results.csv") -> Path:
    if explicit:
        return Path(explicit)
    return exp02_root() / "results" / "raw" / name


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    pd.DataFrame(rows, columns=FIELDS).to_csv(
        path, mode="a" if not write_header else "w", header=write_header, index=False
    )


def outcome_row(experiment: str, outcome, gt_indices, policy_type: str, selectivity: float,
                sigma: float, insufficient: bool, actual_count: int,
                actual_selectivity: float, seed: int) -> dict:
    return {
        "experiment": experiment,
        "algorithm": outcome.algorithm,
        "bridge_r": outcome.bridge_r if outcome.bridge_r is not None else "",
        "policy_type": policy_type,
        "selectivity_pct": round(float(selectivity) * 100, 4),
        "sigma": float(sigma),
        "budget": outcome.budget,
        "query_id": outcome.query_id,
        "recall_at_10": recall_at_k(gt_indices, outcome.result_ids),
        "gt_size": len(gt_indices),
        "insufficient_gt": int(bool(insufficient)),
        "distance_evaluations": outcome.distance_evaluations,
        "unique_discovered_nodes": outcome.unique_discovered_nodes,
        "unique_visited_nodes": outcome.unique_visited_nodes,
        "expanded_nodes": outcome.expanded_nodes,
        "neighbor_checks": outcome.neighbor_checks,
        "candidate_count": outcome.candidate_count,
        "candidate_id_bytes": outcome.candidate_id_bytes,
        "candidate_meta_bytes": outcome.candidate_meta_bytes,
        "candidate_vector_bytes": outcome.candidate_vector_bytes,
        "candidate_transfer_bytes": outcome.candidate_transfer_bytes,
        "legal_candidates_count": outcome.legal_candidates_count,
        "returned_count": outcome.returned_count,
        "stop_position": outcome.stop_position,
        "termination_reason": outcome.termination_reason,
        "actual_authorized_count": actual_count,
        "actual_selectivity": actual_selectivity,
        "entry_node_id": outcome.entry_node,
        "trace_sha16": outcome.trace_sha,
        "seed": seed,
    }


def make_policy(config: Config, dataset, distribution: str, selectivity: float):
    return build_policy(
        dataset, distribution, selectivity,
        float(config["policies"]["clustered_sigma"]),
        int(config["policies"]["clustered_centers"]),
    )


def variants(config: Config):
    return algorithm_variants(config)


def run_log_for(query, vectors, graph, config, algorithm, bridge_r, mask):
    return run_log(query, vectors, graph, config, algorithm, policy_mask=mask, bridge_r=bridge_r)


def derive_for(log, config, budget, mask, query_id):
    return derive(log, config, budget, policy_mask=mask, query_id=query_id)
