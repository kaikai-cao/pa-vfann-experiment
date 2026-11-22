"""EXP-02 algorithm entry points.

E1: Adaptive Post-filter -- policy-aware early stop, distance-only priority.
E2: Predicate-aware Search -- custom controlled bridge, not ACORN/RACORN.
E3: Fixed-trace Private Filtering -- search plan is independent of policy.

All three share the same lazy distance meter, public fixed entry and expansion
budget. E3's function signature deliberately has NO policy argument.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .config import Config, load_config
from .lazy_search import SearchLog, SearchOutcome, derive_outcome, traverse


def entry_from_seed(seed: int, n_vectors: int) -> int:
    """Regenerate the public entry from the master seed (EXP-02 tag 0x4558503032)."""
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(seed), 0x4558503032])))
    return int(rng.integers(0, int(n_vectors)))


def fixed_entry(config: Config) -> int:
    """Return the literal pinned entry; verify it against the seed derivation."""
    n = int(config["data"]["n_vectors"])
    seed = int(config["data"]["seed"])
    literal = int(config["search"]["entry_node_id"])
    if not 0 <= literal < n:
        raise ValueError(f"entry_node_id out of range: {literal}")
    if literal != entry_from_seed(seed, n):
        raise ValueError("entry_node_id does not match seed derivation")
    return literal


def run_log(
    query: np.ndarray,
    vectors: np.ndarray,
    graph,
    config: Config,
    algorithm: str,
    *,
    policy_mask: np.ndarray | None = None,
    bridge_r: int | None = None,
    max_expansions: int | None = None,
) -> SearchLog:
    """Run one algorithm at the maximum budget used by the experiment."""
    mode = {"E1_POSTFILTER": "E1", "E2_BRIDGE": "E2", "E3_FIXED_TRACE": "E3"}.get(algorithm, algorithm)
    if max_expansions is None:
        max_expansions = max(int(b) for b in config["search"]["budgets"])
    return traverse(
        query, vectors, graph, fixed_entry(config), max_expansions,
        mode=mode,
        policy_mask=policy_mask if mode != "E3" else None,
        bridge_r=bridge_r,
        top_k=int(config["search"]["top_k"]),
        min_expansions=int(config["search"]["min_expansions_before_stop"]),
    )


def derive(
    log: SearchLog,
    config: Config,
    budget: int,
    *,
    policy_mask: np.ndarray | None = None,
    query_id: int = 0,
    note: str = "",
) -> SearchOutcome:
    return derive_outcome(
        log, budget, policy_mask, int(config["search"]["top_k"]),
        int(config["data"]["dimension"]), query_id=query_id, note=note,
    )


def run_search(
    query: np.ndarray,
    vectors: np.ndarray,
    graph,
    config: Config,
    algorithm: str,
    budget: int,
    *,
    policy_mask: np.ndarray | None = None,
    bridge_r: int | None = None,
    query_id: int = 0,
) -> SearchOutcome:
    """Convenience API for tests: run directly at ``budget``."""
    log = run_log(
        query, vectors, graph, config, algorithm,
        policy_mask=policy_mask, bridge_r=bridge_r, max_expansions=budget,
    )
    return derive(log, config, budget, policy_mask=policy_mask, query_id=query_id)


def algorithm_variants(config: Config) -> list[tuple[str, int | None]]:
    """(algorithm label, bridge r) list in a fixed reporting order."""
    variants = [("E1_POSTFILTER", None)]
    variants += [("E2_BRIDGE", int(r)) for r in config["search"]["bridge_r_values"]]
    variants.append(("E3_FIXED_TRACE", None))
    return variants
