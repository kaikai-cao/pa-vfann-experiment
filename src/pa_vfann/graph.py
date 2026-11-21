"""Reproducible exact-kNN graph used by all three search strategies.

The graph is built once per dataset. Forward edges are the exact ``degree``
nearest neighbours under squared L2 (self excluded). With
``add_reverse_edges=true`` the adjacency used by search is the *undirected
union* of forward and reverse edges; reverse edges are added for reproducibility
and connectivity only. This graph is a controlled simulator and is NOT HNSW.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dataset import Dataset
from .config import Config


@dataclass(frozen=True)
class Graph:
    adjacency: tuple[tuple[int, ...], ...]  # undirected union, sorted, self-free
    forward_adjacency: tuple[tuple[int, ...], ...]
    degree: int
    symm: bool
    connected_components: int
    max_undirected_degree: int
    construction: str = "exact_knn_l2_union_reverse"

    @property
    def n_nodes(self) -> int:
        return len(self.adjacency)


def _exact_knn_forward(vectors: np.ndarray, degree: int, chunk_size: int) -> list[np.ndarray]:
    n = vectors.shape[0]
    norms = np.einsum("ij,ij->i", vectors, vectors)
    forward: list[np.ndarray] = []
    for start in range(0, n, chunk_size):
        block = vectors[start : start + chunk_size]
        block_norms = np.einsum("ij,ij->i", block, block)
        dist = block_norms[:, None] + norms[None, :] - 2.0 * (block @ vectors.T)
        np.maximum(dist, 0.0, out=dist)
        k = min(degree + 1, n)
        cand = np.argpartition(dist, kth=k - 1, axis=1)[:, :k]
        for local, row in enumerate(cand):
            order = row[np.argsort(dist[local, row], kind="stable")]
            order = order[order != start + local][:degree]
            forward.append(np.asarray(order, dtype=np.int64))
    return forward


def _connected_components(adjacency: tuple[tuple[int, ...], ...]) -> int:
    n = len(adjacency)
    seen = np.zeros(n, dtype=bool)
    count = 0
    stack: list[int] = []
    for start in range(n):
        if seen[start]:
            continue
        count += 1
        seen[start] = True
        stack.append(start)
        while stack:
            node = stack.pop()
            for nxt in adjacency[node]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
    return count


def build_graph(dataset: Dataset, config: Config) -> Graph:
    gcfg = config["graph"]
    if not gcfg.get("exact_knn", True):
        raise ValueError("EXP-01 only supports the exact-kNN graph")
    degree = int(gcfg["degree"])
    vectors = dataset.vectors
    forward = _exact_knn_forward(vectors, degree, int(gcfg.get("chunk_size", 500)))
    symm = bool(gcfg.get("add_reverse_edges", True))
    if symm:
        merged: list[set[int]] = [set(int(v) for v in row) for row in forward]
        for src, row in enumerate(forward):
            for dst in row:
                merged[int(dst)].add(src)
        adjacency = tuple(tuple(sorted(row)) for row in merged)
    else:
        adjacency = tuple(tuple(int(v) for v in row) for row in forward)
    return Graph(
        adjacency=adjacency,
        forward_adjacency=tuple(tuple(int(v) for v in row) for row in forward),
        degree=degree,
        symm=symm,
        connected_components=_connected_components(adjacency),
        max_undirected_degree=max(len(row) for row in adjacency),
    )
