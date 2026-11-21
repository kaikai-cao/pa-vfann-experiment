"""Shared helpers for the two batch experiment runners."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from pa_vfann.config import Config, default_config_path, load_config
from pa_vfann.dataset import Dataset, build_dataset, squared_l2_to_all
from pa_vfann.graph import Graph, build_graph
from pa_vfann.metrics import recall_at_k
from pa_vfann.policies import build_policy
from pa_vfann.search_common import SearchOutcome, truncate_outcome

RAW_CSV_NAME = "experiment_results.csv"
FIELDS = [
    "experiment", "algorithm", "bridge_r", "policy_type", "selectivity_pct",
    "sigma", "budget", "query_id", "recall_at_10", "gt_size",
    "insufficient_gt", "unique_visited_count", "expanded_nodes_count",
    "neighbor_checks_count", "stop_position", "legal_candidates_count",
    "returned_count", "actual_authorized_count", "actual_selectivity",
    "trace_sha16", "seed",
]


def result_path(config: Config) -> Path:
    return config.path.resolve().parents[1] / "results" / "raw" / RAW_CSV_NAME


def prepare(config: Config) -> tuple[Dataset, Graph, "object"]:
    dataset = build_dataset(config)
    qdist = squared_l2_to_all(dataset.query_vectors, dataset.vectors)
    graph = build_graph(dataset, config)
    return dataset, graph, qdist


def make_row(
    experiment: str,
    outcome: SearchOutcome,
    gt_indices,
    insufficient: bool,
    policy_type: str,
    selectivity: float,
    sigma: float,
    actual_count: int,
    actual_selectivity: float,
    seed: int,
) -> dict:
    return {
        "experiment": experiment,
        "algorithm": outcome.algorithm,
        "bridge_r": outcome.bridge_r if outcome.bridge_r is not None else "",
        "policy_type": policy_type,
        "selectivity_pct": round(float(selectivity) * 100, 4),
        "sigma": float(sigma),
        "budget": outcome.budget,
        "query_id": outcome.query_id,
        "recall_at_10": recall_at_k(outcome, gt_indices),
        "gt_size": len(gt_indices),
        "insufficient_gt": int(bool(insufficient)),
        "unique_visited_count": outcome.unique_visited_count,
        "expanded_nodes_count": outcome.expanded_nodes_count,
        "neighbor_checks_count": outcome.neighbor_checks_count,
        "stop_position": outcome.stop_position,
        "legal_candidates_count": outcome.legal_candidates_count,
        "returned_count": outcome.returned_count,
        "actual_authorized_count": actual_count,
        "actual_selectivity": actual_selectivity,
        "trace_sha16": hashlib.sha256(
            ",".join(str(v) for v in outcome.visited_nodes).encode("ascii")
        ).hexdigest()[:16],
        "seed": seed,
    }


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    pd.DataFrame(rows, columns=FIELDS).to_csv(
        path, mode="a" if not write_header else "w", header=write_header, index=False
    )


def cli_config(argv: list[str] | None = None) -> Config:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(default_config_path()))
    args = parser.parse_args(argv)
    return load_config(args.config)


def all_budget_outcomes(
    full: SearchOutcome,
    budgets: list[int],
    graph: Graph,
    qdist_row,
    policy_mask,
    top_k: int,
) -> list[SearchOutcome]:
    return [
        truncate_outcome(full, budget, graph, qdist_row, policy_mask, top_k)
        for budget in budgets
    ]


def policy_for(config: Config, dataset: Dataset, policy_type: str, selectivity: float, sigma: float):
    return build_policy(
        dataset,
        policy_type,
        selectivity,
        sigma,
        int(config["policies"]["clustered_centers"]),
    )
