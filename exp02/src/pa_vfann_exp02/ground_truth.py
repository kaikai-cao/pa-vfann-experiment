"""Independent filtered exact Top-K ground truth for EXP-02.

This is the ONLY module allowed to compute a full query-to-database distance
table, and it runs outside the ANN search state machine. Its cost is never
recorded in distance_evaluations or any other ANN cost column.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .exp01_bridge import squared_l2_to_all


@dataclass(frozen=True)
class GroundTruth:
    indices: tuple[tuple[int, ...], ...]
    distances: tuple[tuple[float, ...], ...]
    sizes: tuple[int, ...]
    authorized_counts: tuple[int, ...]
    k: int

    def insufficient(self, query_id: int) -> bool:
        return self.authorized_counts[query_id] < self.k


def build_ground_truth(
    query_vectors: np.ndarray,
    vectors: np.ndarray,
    authorized_mask: np.ndarray,
    top_k: int,
    chunk_size: int = 500,
) -> GroundTruth:
    full_distances = squared_l2_to_all(query_vectors, vectors, chunk_size=chunk_size)
    mask = np.asarray(authorized_mask, dtype=bool)
    legal = np.flatnonzero(mask)
    indices: list[tuple[int, ...]] = []
    distances: list[tuple[float, ...]] = []
    sizes: list[int] = []
    for row in full_distances:
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
        indices=tuple(indices), distances=tuple(distances), sizes=tuple(sizes),
        authorized_counts=(int(legal.size),) * len(full_distances), k=int(top_k),
    )
