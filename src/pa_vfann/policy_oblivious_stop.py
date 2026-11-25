"""EXP-09: policy-oblivious adaptive stopping over the public E3 plan.

Scope (deliberately narrow):
  * The stop decision reads only the query distance row, the already-visited
    node sequence and fixed hyper-parameters. It never receives an
    authorization mask, policy id, filter result or legal-result count.
  * The secret filter is applied AFTER traversal, exactly as in E3.
  * This is a strategy-obliviousness property, NOT query privacy, output
    privacy or full access-pattern privacy.

Two strategies:
  T1  fixed visit-count truncation at c = fraction * B.
  T2  distance-convergence stop with k = 10, d10(t) = k-th smallest distance
      among the visited nodes at visit count t, and

          delta_t = (d10(t-m) - d10(t)) / max(|d10(t-m)|, 1e-12)

      Stop when m consecutive checks have delta_t <= epsilon, provided at
      least min_fraction * B nodes were visited and enough candidates exist
      to compute d10. Otherwise continue to the full budget B.

Both strategies are supplied as ``stop_when`` predicates to
``search_common.best_first_search``, so the visited sequence remains the exact
public best-first plan and cost counters are computed by the original code.
"""

from __future__ import annotations

import time
from bisect import insort
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .graph import Graph
from .search_common import SearchOutcome, assemble_outcome, best_first_search
from .secret_filter import simulated_secret_filter


@dataclass(frozen=True)
class StopDecision:
    """Audit record for one policy-oblivious stop decision."""

    stop_position: int
    stop_reason: str                       # fixed_count | distance_converged | max_budget
    checks_evaluated: int
    judgement_ns: int
    delta_trace: tuple[tuple[int, float], ...] = ()   # (visit_count, delta_t)


class T1FixedCountStopper:
    """Stop once ``round(fraction * budget)`` unique nodes are visited."""

    def __init__(self, budget: int, fraction: float) -> None:
        if not 0.0 < fraction <= 1.0:
            raise ValueError("fraction must lie in (0, 1]")
        self.budget = max(int(budget), 0)
        self.fraction = float(fraction)
        self.limit = max(1, int(round(float(fraction) * self.budget))) if self.budget else 0
        self._stop_position = 0
        self._stop_reason = "max_budget"
        self._judgement_ns = 0

    def __call__(self, visited: Sequence[int]) -> bool:
        t0 = time.perf_counter_ns()
        t = len(visited)
        stop = bool(self.budget) and t >= self.limit
        self._judgement_ns += time.perf_counter_ns() - t0
        if stop:
            self._stop_position = t
            self._stop_reason = "fixed_count"
        return stop

    def decision(self, final_visited_count: int) -> StopDecision:
        position = self._stop_position or final_visited_count
        return StopDecision(
            stop_position=position,
            stop_reason=self._stop_reason,
            checks_evaluated=final_visited_count,
            judgement_ns=self._judgement_ns,
        )


class T2DistanceConvergenceStopper:
    """Stop when the k-th nearest visited distance stops improving.

    The predicate accepts only the visited node sequence. The query distance
    row is bound at construction time; no policy object is ever passed in.
    """

    def __init__(
        self,
        query_distances_row: np.ndarray,
        budget: int,
        k: int = 10,
        min_fraction: float = 0.6,
        m: int = 8,
        epsilon: float = 0.001,
    ) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        if m < 1:
            raise ValueError("m must be >= 1")
        if not 0.0 < min_fraction <= 1.0:
            raise ValueError("min_fraction must lie in (0, 1]")
        if epsilon < 0.0:
            raise ValueError("epsilon must be >= 0")
        self.row = np.asarray(query_distances_row)
        self.budget = max(int(budget), 0)
        self.k = int(k)
        self.min_visits = max(1, int(np.ceil(float(min_fraction) * self.budget))) if self.budget else 0
        self.m = int(m)
        self.epsilon = float(epsilon)
        self._sorted_distances: list[float] = []
        self._processed = 0
        self._d10: dict[int, float] = {}
        self._streak = 0
        self._checks = 0
        self._deltas: list[tuple[int, float]] = []
        self._stop_position = 0
        self._stop_reason = "max_budget"
        self._judgement_ns = 0

    def _ingest(self, visited: Sequence[int]) -> None:
        """Maintain sorted distances of all visited nodes incrementally."""
        t = len(visited)
        if t <= self._processed:
            return
        for node in visited[self._processed:t]:
            insort(self._sorted_distances, float(self.row[int(node)]))
        self._processed = t
        if t >= self.k:
            self._d10[t] = float(self._sorted_distances[self.k - 1])

    def __call__(self, visited: Sequence[int]) -> bool:
        t0 = time.perf_counter_ns()
        t = len(visited)
        self._ingest(visited)
        # Guard: minimum visits AND enough history for d10(t-m).
        if t < self.min_visits or t < self.k + self.m:
            self._judgement_ns += time.perf_counter_ns() - t0
            return False
        prev = t - self.m
        if prev not in self._d10 or t not in self._d10:
            self._judgement_ns += time.perf_counter_ns() - t0
            return False
        d_prev = self._d10[prev]
        d_now = self._d10[t]
        delta = (d_prev - d_now) / max(abs(d_prev), 1e-12)
        self._checks += 1
        self._deltas.append((t, float(delta)))
        self._streak = self._streak + 1 if delta <= self.epsilon else 0
        stop = self._streak >= self.m
        self._judgement_ns += time.perf_counter_ns() - t0
        if stop:
            self._stop_position = t
            self._stop_reason = "distance_converged"
        return stop

    def decision(self, final_visited_count: int) -> StopDecision:
        return StopDecision(
            stop_position=self._stop_position or final_visited_count,
            stop_reason=self._stop_reason,
            checks_evaluated=self._checks,
            judgement_ns=self._judgement_ns,
            delta_trace=tuple(self._deltas),
        )


Stopper = T1FixedCountStopper | T2DistanceConvergenceStopper


def run_stop_search(
    algorithm: str,
    query_distances_row: np.ndarray,
    graph: Graph,
    budget: int,
    policy_mask: np.ndarray,
    top_k: int,
    stopper: Stopper,
    query_id: int = 0,
    filter_fn=simulated_secret_filter,
) -> tuple[SearchOutcome, StopDecision, int]:
    """Run one policy-oblivious stop search.

    Returns (outcome, decision, wall_ns). The policy mask is used ONLY by the
    post-traversal simulated secret filter; it is never exposed to stopper.
    """
    t0 = time.perf_counter_ns()
    visited, expanded, checks = best_first_search(
        query_distances_row, graph, budget, stop_when=stopper
    )
    decision = stopper.decision(len(visited))
    legal_topk, legal_total = filter_fn(visited, query_distances_row, policy_mask, top_k)
    outcome = assemble_outcome(
        algorithm=algorithm,
        query_id=query_id,
        budget=budget,
        bridge_r=None,
        visited=visited,
        expanded=expanded,
        neighbor_checks=checks,
        legal_ids=legal_topk,
        query_distances_row=query_distances_row,
        top_k=top_k,
        policy_dependent=False,
        legal_candidates_count=legal_total,
        note=f"policy-oblivious stop: {decision.stop_reason} at {decision.stop_position}",
    )
    return outcome, decision, time.perf_counter_ns() - t0
