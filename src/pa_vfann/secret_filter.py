"""Simulated secret filtering interface (NOT a cryptographic implementation).

This module is the explicit boundary between the public search plan and the
authorization predicate. In EXP-01 the predicate is evaluated locally by a
trusted simulator; no MPC, ORAM, ZK proof or private information retrieval is
implemented or claimed. The only property under test is that the public plan
does not observe authorization bits.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

SIMULATED_SECRET_FILTER = True


def simulated_secret_filter(
    visited_nodes: Sequence[int],
    query_distances_row: np.ndarray,
    authorization_bits: np.ndarray,
    top_k: int,
) -> tuple[list[int], int]:
    """Return (ranked authorized Top-K ids, total authorized count among visited).

    The second value is the legal-candidate count used for reporting; it is not
    fed back into the search plan.
    """
    row = np.asarray(query_distances_row)
    bits = np.asarray(authorization_bits, dtype=bool)
    legal = [int(v) for v in visited_nodes if bits[int(v)]]
    legal.sort(key=lambda v: (float(row[v]), v))
    return legal[:top_k], len(legal)
