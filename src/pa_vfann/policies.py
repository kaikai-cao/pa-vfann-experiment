"""Authorization policy label generation (Random and Clustered).

Labels are derived from the master seed plus explicit policy parameters, so the
same policy can be regenerated in any order of experiments. ``sigma`` only
matters for the clustered policy: smaller sigma means stronger spatial
correlation between authorization and vector position.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dataset import Dataset

DIST_CODE = {"random": 1, "clustered": 2}


@dataclass(frozen=True)
class Policy:
    name: str
    selectivity: float
    sigma: float
    mask: np.ndarray            # bool, shape (n,)
    actual_count: int
    actual_selectivity: float
    center_ids: tuple[int, ...]


def _centers(rng: np.random.Generator, n: int, n_centers: int) -> tuple[int, ...]:
    return tuple(int(v) for v in rng.choice(n, size=min(n_centers, n), replace=False))


def build_policy(
    dataset: Dataset,
    distribution: str,
    selectivity: float,
    sigma: float,
    n_centers: int,
) -> Policy:
    if distribution not in DIST_CODE:
        raise ValueError(f"unknown policy distribution: {distribution}")
    if not 0.0 <= selectivity <= 1.0:
        raise ValueError("selectivity must lie in [0, 1]")
    n = dataset.n
    seed_sequence = np.random.SeedSequence(
        [dataset.master_seed, DIST_CODE[distribution], int(round(selectivity * 10000)), int(sigma)]
    )
    rng = np.random.Generator(np.random.PCG64(seed_sequence))
    target = int(round(selectivity * n))
    mask = np.zeros(n, dtype=bool)
    centers: tuple[int, ...] = ()

    if distribution == "random":
        if target:
            mask[rng.choice(n, size=target, replace=False)] = True
    else:
        centers = _centers(rng, n, n_centers)
        if target:
            center_vectors = dataset.vectors[list(centers)]
            d2 = np.min(
                np.maximum(
                    np.einsum("ij,ij->i", dataset.vectors, dataset.vectors)[:, None]
                    + np.einsum("ij,ij->i", center_vectors, center_vectors)[None, :]
                    - 2.0 * (dataset.vectors @ center_vectors.T),
                    0.0,
                ),
                axis=1,
            )
            weights = np.exp(-d2 / (2.0 * float(sigma) ** 2))
            weights = weights / weights.sum()
            mask[rng.choice(n, size=target, replace=False, p=weights)] = True

    actual = int(mask.sum())
    return Policy(
        name=distribution,
        selectivity=float(selectivity),
        sigma=float(sigma),
        mask=mask,
        actual_count=actual,
        actual_selectivity=actual / n,
        center_ids=centers,
    )
