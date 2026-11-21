"""Independent filtered exact Top-K ground truth.

Ground truth is computed by brute-force sorting over all authorized records.
No ANN search algorithm is involved, and no result is fabricated when the
authorized set has fewer than K records.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GroundTruth:
    indices: tuple[tuple[int, ...], ...]   # per query, at most K
    distances: tuple[tuple[float, ...], ...]
    sizes: tuple[int, ...]
    authorized_counts: tuple[int, ...]
    k: int = 10

    @property
    def n_queries(self) -> int:
        return len(self.indices)

    def insufficient(self, query_id: int) -> bool:
        """True when fewer than K authorized records exist for this query."""
        return self.authorized_counts[query_id] < self.k


def filtered_exact_topk(
    query_distances: np.ndarray,
    authorized_mask: np.ndarray,
    top_k: int,
) -> GroundTruth:
    """Compute filtered exact Top-K for each query.

    Ties are broken by ascending record id, making the output deterministic.
    """
    qdist = np.asarray(query_distances)
    authorized = np.asarray(authorized_mask, dtype=bool)
    if qdist.ndim != 2 or authorized.shape[0] != qdist.shape[1]:
        raise ValueError("shape mismatch between query_distances and authorized_mask")
    indices: list[tuple[int, ...]] = []
    distances: list[tuple[float, ...]] = []
    sizes: list[int] = []
    counts: list[int] = []
    legal = np.flatnonzero(authorized)
    for row in qdist:
        counts.append(int(legal.size))
        if legal.size == 0:
            indices.append(())
            distances.append(())
            sizes.append(0)
            continue
        order = legal[np.lexsort((legal, row[legal]))][:top_k]
        indices.append(tuple(int(v) for v in order))
        distances.append(tuple(float(row[v]) for v in order))
        sizes.append(int(order.size))
    return GroundTruth(
        indices=tuple(indices),
        distances=tuple(distances),
        sizes=tuple(sizes),
        authorized_counts=tuple(counts),
        k=int(top_k),
    )
