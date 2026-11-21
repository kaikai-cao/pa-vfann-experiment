import numpy as np

from pa_vfann.graph import build_graph


def test_graph_forward_degree_and_no_self_loops(small_graph):
    assert small_graph.n_nodes == 200
    for row in small_graph.forward_adjacency:
        assert len(row) == 8
    for node, row in enumerate(small_graph.forward_adjacency):
        assert node not in row


def test_graph_symmetrized_and_bounded(small_graph):
    for u, row in enumerate(small_graph.adjacency):
        assert u not in row
        assert list(row) == sorted(set(int(v) for v in row))
        for v in row:
            assert u in small_graph.adjacency[v]
    assert small_graph.max_undirected_degree >= small_graph.degree
    assert small_graph.connected_components >= 1


def test_graph_is_reproducible(small_config, small_dataset):
    a = build_graph(small_dataset, small_config)
    b = build_graph(small_dataset, small_config)
    assert a.adjacency == b.adjacency
    assert a.forward_adjacency == b.forward_adjacency
    assert a.construction == "exact_knn_l2_union_reverse"


def test_forward_edges_are_nearest_neighbours(small_config, small_dataset, small_graph):
    v = small_dataset.vectors
    sq = np.sum((v[None, :, :] - v[:, None, :]) ** 2, axis=2)
    for u in (0, 7, 42):
        expected = set(int(x) for x in np.argsort(sq[u], kind="stable")[1 : 1 + small_graph.degree])
        assert set(int(x) for x in small_graph.forward_adjacency[u]) == expected
