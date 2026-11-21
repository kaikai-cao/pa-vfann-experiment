"""Deterministic synthetic dataset and query generation.

Vectors are i.i.d. standard normal (float32). A spatially clustered policy is
still meaningful on isotropic data: cluster centres are fixed sample points
and affinity is an explicit function of L2 distance to the nearest centre.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Config


@dataclass(frozen=True)
class Dataset:
    vectors: np.ndarray          # (n, d), float32
    query_vectors: np.ndarray    # (nq, d), float32
    master_seed: int

    @property
    def n(self) -> int:
        return int(self.vectors.shape[0])

    @property
    def n_queries(self) -> int:
        return int(self.query_vectors.shape[0])


def build_dataset(config: Config) -> Dataset:
    dcfg = config["data"]
    qcfg = config["query"]
    n = int(dcfg["n_vectors"])
    dim = int(dcfg["dimension"])
    seed = int(dcfg["seed"])
    if dcfg.get("distribution", "standard_normal") != "standard_normal":
        raise ValueError("only standard_normal is supported in EXP-01")
    streams = np.random.SeedSequence(seed).spawn(2)
    vectors = np.asarray(np.random.Generator(np.random.PCG64(streams[0])).standard_normal((n, dim)), dtype=np.float32)
    queries = np.asarray(np.random.Generator(np.random.PCG64(streams[1])).standard_normal((int(qcfg["n_queries"]), dim)), dtype=np.float32)
    return Dataset(vectors=vectors, query_vectors=queries, master_seed=seed)


def squared_l2_to_all(query_vectors: np.ndarray, vectors: np.ndarray, chunk_size: int = 500) -> np.ndarray:
    """Return (n_queries, n_vectors) squared L2 distances in float32."""
    vectors = np.asarray(vectors, dtype=np.float32)
    queries = np.asarray(query_vectors, dtype=np.float32)
    norms = np.einsum("ij,ij->i", vectors, vectors)
    out = np.empty((queries.shape[0], vectors.shape[0]), dtype=np.float32)
    for start in range(0, queries.shape[0], chunk_size):
        block = queries[start : start + chunk_size]
        block_norms = np.einsum("ij,ij->i", block, block)
        dist = block_norms[:, None] + norms[None, :] - 2.0 * (block @ vectors.T)
        np.maximum(dist, 0.0, out=dist)
        out[start : start + block.shape[0]] = dist.astype(np.float32)
    return out
