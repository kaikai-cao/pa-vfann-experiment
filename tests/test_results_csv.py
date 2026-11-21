"""Result integrity test; skipped until the full experiment has been run."""

from pathlib import Path

import pandas as pd
import pytest

RAW = Path(__file__).resolve().parents[1] / "results" / "raw" / "experiment_results.csv"
REQUIRED = {
    "experiment", "algorithm", "bridge_r", "policy_type", "selectivity_pct",
    "budget", "query_id", "recall_at_10", "unique_visited_count",
    "expanded_nodes_count", "neighbor_checks_count", "stop_position",
    "legal_candidates_count", "returned_count", "gt_size", "insufficient_gt",
}


def test_experiment_results_csv_integrity():
    if not RAW.exists():
        pytest.skip("full experiment not run yet")
    df = pd.read_csv(RAW)
    assert len(df) > 0
    assert REQUIRED <= set(df.columns)
    assert df["recall_at_10"].between(0.0, 1.0).all()
    assert (df["unique_visited_count"] <= df["budget"]).all()
    assert (df["returned_count"] <= 10).all()
    assert not df[list(REQUIRED)].isna().all(axis=1).any()
    for column in ("experiment", "algorithm", "policy_type"):
        assert df[column].notna().all()
