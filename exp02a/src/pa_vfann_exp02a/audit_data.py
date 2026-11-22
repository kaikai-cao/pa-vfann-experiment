"""Read-only access to the frozen EXP-02 raw results.

No ANN search is re-run here. Candidate counts, recall values and leakage
metrics are consumed from exp02/results/raw/experiment_results.csv exactly as
committed at 29ec958.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from .config import AuditConfig


def load_raw(config: AuditConfig) -> pd.DataFrame:
    path = config.resolve("raw_csv")
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, low_memory=False)


def selectivity_rows(raw: pd.DataFrame, algorithm: str = "E3_FIXED_TRACE") -> pd.DataFrame:
    return raw[(raw["experiment"] == "selectivity") & (raw["algorithm"] == algorithm)].copy()


def leakage_rows(raw: pd.DataFrame) -> pd.DataFrame:
    return raw[raw["experiment"] == "leakage"].copy()


def query_set_hash(ids) -> str:
    vals = sorted(int(v) for v in ids)
    raw = ",".join(str(v) for v in vals).encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:16]


def recall_target_query_sets(raw: pd.DataFrame, target: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit whether 'cost at target recall' uses one query set or two.

    EXP-02's budget table uses cell-mean recall >= target for the budget, and
    a different all-query mean for the reported cost; its
    ``min_*_any_query_at_target`` column uses only queries that individually
    reached the target. This function makes both populations explicit.
    """
    sel = raw[raw["experiment"] == "selectivity"].copy()
    keys = ["policy_type", "selectivity_pct", "algorithm", "budget"]
    detailed: list[dict] = []
    for key, group in sel.groupby(keys, sort=True):
        reached = group[group["recall_at_10"] >= target]
        detailed.append({
            "policy_type": key[0],
            "selectivity_pct": float(key[1]),
            "algorithm": key[2],
            "budget": int(key[3]),
            "n_queries_total": int(len(group)),
            "n_queries_reached": int(len(reached)),
            "cell_mean_recall": float(group["recall_at_10"].mean()),
            "cell_reached": int(float(group["recall_at_10"].mean()) >= target),
            "reached_query_set_sha16": query_set_hash(reached["query_id"]),
            "distance_mean_all_queries": float(group["distance_evaluations"].mean()),
            "distance_mean_reached_queries_only": float(reached["distance_evaluations"].mean()) if len(reached) else float("nan"),
            "candidate_count_mean_all_queries": float(group["candidate_count"].mean()),
            "candidate_count_mean_reached_queries_only": float(reached["candidate_count"].mean()) if len(reached) else float("nan"),
        })
    detail = pd.DataFrame(detailed).sort_values(keys)

    cell_keys = keys[:-1]
    summary_rows: list[dict] = []
    for key, group in detail.groupby(cell_keys, sort=True):
        cell_hit = group[group["cell_reached"] == 1]
        any_hit = group[group["n_queries_reached"] > 0]
        s = group.sort_values("budget")
        first_any = s[s["n_queries_reached"] > 0].head(1)
        summary_rows.append({
            "policy_type": key[0],
            "selectivity_pct": float(key[1]),
            "algorithm": key[2],
            # Population A: cell mean over ALL 200 queries.
            "budget_cell_mean_reached": int(cell_hit["budget"].min()) if len(cell_hit) else "NOT_REACHED",
            "distance_at_cell_mean_reached_all_queries": float(cell_hit["distance_mean_all_queries"].min()) if len(cell_hit) else float("nan"),
            "candidates_at_cell_mean_reached_all_queries": float(cell_hit["candidate_count_mean_all_queries"].min()) if len(cell_hit) else float("nan"),
            "reached_queries_at_cell_budget": int(cell_hit["n_queries_reached"].min()) if len(cell_hit) else 0,
            # Population B: only queries that individually reached the target.
            "budget_any_query_reached": int(first_any["budget"].iloc[0]) if len(first_any) else "NOT_REACHED",
            "distance_at_any_query_reached_reached_only": float(first_any["distance_mean_reached_queries_only"].iloc[0]) if len(first_any) else float("nan"),
            "candidates_at_any_query_reached_reached_only": float(first_any["candidate_count_mean_reached_queries_only"].iloc[0]) if len(first_any) else float("nan"),
            "n_queries_reached_at_that_budget": int(first_any["n_queries_reached"].iloc[0]) if len(first_any) else 0,
            "query_populations_identical": int(
                len(cell_hit) > 0 and len(first_any) > 0
                and int(cell_hit["budget"].min()) == int(first_any["budget"].iloc[0])
                and int(cell_hit["n_queries_reached"].min()) == int(first_any["n_queries_reached"].iloc[0])
            ),
        })
    return detail, pd.DataFrame(summary_rows).sort_values(cell_keys)


def candidate_cost_frame(raw: pd.DataFrame, algorithm: str = "E3_FIXED_TRACE") -> pd.DataFrame:
    """One row per (policy, selectivity, budget) with candidate count stats."""
    sel = selectivity_rows(raw, algorithm)
    keys = ["policy_type", "selectivity_pct", "budget"]
    rows = []
    for key, group in sel.groupby(keys, sort=True):
        counts = group["candidate_count"].astype(float)
        rows.append({
            "policy_type": key[0],
            "selectivity_pct": float(key[1]),
            "budget": int(key[2]),
            "n_queries": int(len(group)),
            "candidate_count_mean": float(counts.mean()),
            "candidate_count_p95": float(counts.quantile(0.95)),
            "candidate_count_min": float(counts.min()),
            "candidate_count_max": float(counts.max()),
        })
    return pd.DataFrame(rows).sort_values(keys)
