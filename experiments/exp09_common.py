"""Shared helpers for EXP-09 (policy-oblivious adaptive stopping).

The tuning and confirmation phases are two separate programs. The confirmation
program reads the frozen parameter file written by the tuning program and never
inspects tuning results, so no repeated tuning on the confirmation set is
possible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from pa_vfann.policy_oblivious_stop import (
    StopDecision,
    T1FixedCountStopper,
    T2DistanceConvergenceStopper,
    run_stop_search,
)

TOPOLOGIES = ("random", "clustered")
SELECTIVITIES = (0.01, 0.10, 0.30)
BUDGETS = (100, 200, 500)
T1_FRACTIONS = (0.6, 0.8)
T2_GRID = tuple((m, eps) for m in (8, 16) for eps in (0.001, 0.005))
MAX_PLAN_BUDGET = 500

FIELDS = [
    "phase", "topology", "selectivity_pct", "budget", "method", "params",
    "query_id", "split", "algorithm", "recall_at_10", "gt_size", "insufficient_gt",
    "unique_visited_count", "neighbor_checks_count", "expanded_nodes_count",
    "stop_position", "stop_reason", "wall_ns", "judgement_ns", "delta_checks",
    "trace_sha16", "seed", "sigma",
]

INV_FIELDS = [
    "phase", "selectivity_pct", "budget", "method", "params", "query_id",
    "policy_a", "policy_b", "trace_a_sha16", "trace_b_sha16", "identical",
    "L_set", "L_seq", "stop_position_delta", "L_output_ids",
]


class FullBudgetStopper:
    """C0 reference: never stop early, same timing path as T1/T2."""

    def __init__(self) -> None:
        self.judgement_ns = 0

    def __call__(self, visited) -> bool:
        return False

    def decision(self, final_visited_count: int) -> StopDecision:
        return StopDecision(
            stop_position=final_visited_count,
            stop_reason="max_budget",
            checks_evaluated=0,
            judgement_ns=self.judgement_ns,
        )


def trace_hash(visited) -> str:
    return hashlib.sha256(
        ",".join(str(int(v)) for v in visited).encode("ascii")
    ).hexdigest()[:16]


def _t2_values(params):
    """Accept either (m, eps) tuple or 'm=X;eps=Y' string."""
    if isinstance(params, str):
        m_s, eps_s = params.split(";")
        return int(m_s.split("=")[1]), float(eps_s.split("=")[1])
    m, eps = params
    return int(m), float(eps)


def make_stopper(method: str, params, row: np.ndarray, budget: int):
    if method == "C0":
        return FullBudgetStopper()
    if method == "T1":
        fraction = float(params.split("=")[1]) if isinstance(params, str) else float(params)
        return T1FixedCountStopper(budget, fraction)
    if method == "T2":
        m, eps = _t2_values(params)
        return T2DistanceConvergenceStopper(
            row, budget, k=10, min_fraction=0.6, m=m, epsilon=eps
        )
    raise ValueError(f"unknown stop method: {method}")


def method_name(method: str, params) -> str:
    if method == "C0":
        return "C0_E3_FULL"
    if method == "T1":
        fraction = float(params.split("=")[1]) if isinstance(params, str) else float(params)
        return f"PO_T1_{fraction:.2f}"
    m, eps = _t2_values(params)
    return f"PO_T2_m{m}_eps{eps}"


def params_for(method: str, params) -> str:
    if method == "C0":
        return "full_budget"
    if method == "T1":
        fraction = float(params.split("=")[1]) if isinstance(params, str) else float(params)
        return f"c={fraction:.2f}"
    m, eps = _t2_values(params)
    return f"m={m};eps={eps}"


def params_key(method: str, params) -> str:
    """Canonical key used to match results with frozen parameters."""
    return params_for(method, params)


def write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=fields).to_csv(path, index=False)


def split_for_query(query_id: int, n_queries: int) -> str:
    """Fixed query-ID split: first half tunes, second half confirms."""
    return "tuning" if int(query_id) < n_queries // 2 else "confirmation"


@dataclass(frozen=True)
class Condition:
    topology: str
    selectivity: float
    budget: int
    policy: object
    gt: object
    plans: dict     # query_id -> plan tuple at MAX_PLAN_BUDGET
    sigma: float
    seed: int


def build_conditions(config, dataset, graph, qdist):
    from experiments.exp_common import policy_for
    from pa_vfann.ground_truth import filtered_exact_topk
    from pa_vfann.search_common import plan_fixed_trace

    top_k = int(config["search"]["top_k"])
    sigma = float(config["policies"]["clustered_sigma"])
    seed = int(config["data"]["seed"])
    plans = {
        q: plan_fixed_trace(qdist[q], graph, MAX_PLAN_BUDGET)
        for q in range(dataset.n_queries)
    }
    conditions: list[Condition] = []
    for topology in TOPOLOGIES:
        for selectivity in SELECTIVITIES:
            policy = policy_for(config, dataset, topology, selectivity, sigma)
            gt = filtered_exact_topk(qdist, policy.mask, top_k)
            for budget in BUDGETS:
                conditions.append(Condition(
                    topology=topology, selectivity=selectivity, budget=budget,
                    policy=policy, gt=gt, plans=plans, sigma=sigma, seed=seed,
                ))
    return conditions, top_k


def run_stop_rows(conditions, qdist, graph, top_k, methods, query_ids, phase):
    from pa_vfann.metrics import recall_at_k

    rows: list[dict] = []
    for ctx in conditions:
        for q in query_ids:
            split = split_for_query(q, 200)
            row = np.asarray(qdist[q])
            for method, params in methods:
                stopper = make_stopper(method, params, row, ctx.budget)
                outcome, decision, wall_ns = run_stop_search(
                    method_name(method, params), row, graph, ctx.budget,
                    ctx.policy.mask, top_k, stopper, q,
                )
                rows.append({
                    "phase": phase,
                    "topology": ctx.topology,
                    "selectivity_pct": round(ctx.selectivity * 100, 4),
                    "budget": ctx.budget,
                    "method": method,
                    "params": params_for(method, params),
                    "query_id": q,
                    "split": split,
                    "algorithm": outcome.algorithm,
                    "recall_at_10": recall_at_k(outcome, ctx.gt.indices[q]),
                    "gt_size": len(ctx.gt.indices[q]),
                    "insufficient_gt": int(ctx.gt.insufficient(q)),
                    "unique_visited_count": outcome.unique_visited_count,
                    "neighbor_checks_count": outcome.neighbor_checks_count,
                    "expanded_nodes_count": outcome.expanded_nodes_count,
                    "stop_position": decision.stop_position,
                    "stop_reason": decision.stop_reason,
                    "wall_ns": int(wall_ns),
                    "judgement_ns": int(decision.judgement_ns),
                    "delta_checks": int(decision.checks_evaluated),
                    "trace_sha16": trace_hash(outcome.visited_nodes),
                    "seed": ctx.seed,
                    "sigma": ctx.sigma,
                })
    return rows


def run_invariance_rows(conditions, qdist, graph, top_k, methods, query_ids, phase,
                        policies_by_key):
    """Compare two policies on the same query/graph/budget/seed.

    Note: output IDs are expected to differ because the post-traversal secret
    filter uses the authorization mask. This is NOT output privacy.
    """
    from pa_vfann.leakage import set_leakage, normalized_edit_distance
    from pa_vfann.search_common import assemble_outcome
    from pa_vfann.secret_filter import simulated_secret_filter

    rows: list[dict] = []
    for ctx in conditions:
        for q in query_ids:
            row = np.asarray(qdist[q])
            for method, params in methods:
                other_key = (
                    ("clustered", ctx.selectivity) if ctx.topology == "random"
                    else ("random", ctx.selectivity)
                )
                outcomes = []
                traces = []
                for policy in (ctx.policy, policies_by_key[other_key]):
                    stopper = make_stopper(method, params, row, ctx.budget)
                    outcome, decision, _ = run_stop_search(
                        method_name(method, params), row, graph, ctx.budget,
                        policy.mask, top_k, stopper, q,
                    )
                    outcomes.append(outcome)
                    traces.append(outcome.visited_nodes)
                a, b = outcomes
                ids_a = set(int(v) for v in a.result_ids if v is not None)
                ids_b = set(int(v) for v in b.result_ids if v is not None)
                rows.append({
                    "phase": phase,
                    "selectivity_pct": round(ctx.selectivity * 100, 4),
                    "budget": ctx.budget,
                    "method": method,
                    "params": params_for(method, params),
                    "query_id": q,
                    "policy_a": ctx.topology,
                    "policy_b": "clustered" if ctx.topology == "random" else "random",
                    "trace_a_sha16": trace_hash(traces[0]),
                    "trace_b_sha16": trace_hash(traces[1]),
                    "identical": int(tuple(traces[0]) == tuple(traces[1])),
                    "L_set": set_leakage(traces[0], traces[1]),
                    "L_seq": normalized_edit_distance(traces[0], traces[1]),
                    "stop_position_delta": abs(a.stop_position - b.stop_position),
                    "L_output_ids": set_leakage(ids_a, ids_b),
                })
    return rows
