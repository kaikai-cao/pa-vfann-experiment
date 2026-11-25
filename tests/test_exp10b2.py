import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "experiments" / "exp10_fiqa_hnswlib"
if str(EXP_DIR) not in sys.path:
    sys.path.insert(0, str(EXP_DIR))

import correct_statistics as cs  # noqa: E402
import rebuild_cluster_masks as rcm  # noqa: E402


def test_not_reached_does_not_enter_reached_only_mean() -> None:
    df = pd.DataFrame(
        [
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q1", "reached": True, "t_star": 6, "normalized_t_star": 0.6, "recall_at_B": 0.9},
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q2", "reached": False, "t_star": None, "normalized_t_star": None, "recall_at_B": 0.4},
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q3", "reached": True, "t_star": 8, "normalized_t_star": 0.8, "recall_at_B": 0.95},
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q4", "reached": False, "t_star": None, "normalized_t_star": None, "recall_at_B": 0.2},
        ]
    )
    out = cs.summarize_oracle_reachability(df, resamples=4, seed=1)
    row = out.iloc[0]
    assert row["reached_count"] == 2
    assert row["not_reached_count"] == 2
    assert math.isclose(float(row["reached_rate"]), 0.5)
    assert math.isclose(float(row["reached_only_mean_normalized_t_star"]), 0.7)
    assert math.isclose(float(row["not_reached_recall_at_B_mean"]), 0.3)


def test_all_not_reached_summary_is_empty_not_one() -> None:
    df = pd.DataFrame(
        [
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q1", "reached": False, "t_star": None, "normalized_t_star": None, "recall_at_B": 0.3},
            {"ef_search": 64, "mask_type": "random", "selectivity": 0.01, "delta": 0.05, "qid": "q2", "reached": False, "t_star": None, "normalized_t_star": None, "recall_at_B": 0.5},
        ]
    )
    row = cs.summarize_oracle_reachability(df, resamples=3, seed=1).iloc[0]
    assert int(row["reached_count"]) == 0
    assert float(row["reached_rate"]) == 0.0
    assert pd.isna(row["reached_only_mean_normalized_t_star"])
    assert pd.isna(row["reached_only_ci_low"])
    assert pd.isna(row["reached_only_ci_high"])


def test_bootstrap_resamples_all_rows_of_a_query_cluster() -> None:
    df = pd.DataFrame(
        {
            "qid": ["a", "a", "b", "b"],
            "metric": [0.0, 0.0, 1.0, 1.0],
        }
    )
    # Replicate 0 draws query a twice; replicate 1 draws query b twice.
    indices = np.array([[0, 0], [1, 1]], dtype=np.int64)
    mean, low, high, nq = cs.cluster_bootstrap_mean(df, "qid", "metric", indices=indices)
    assert mean == 0.5
    assert math.isclose(low, 0.0, abs_tol=0.05)
    assert math.isclose(high, 1.0, abs_tol=0.05)
    assert nq == 2


def test_paired_diff_aligns_on_query_id() -> None:
    keys = ["qid", "selectivity", "seed", "ef_search"]
    left = pd.DataFrame(
        [
            {"qid": "q1", "selectivity": 0.1, "seed": 2026, "ef_search": 64, "metric": 0.1},
            {"qid": "q1", "selectivity": 0.1, "seed": 2026, "ef_search": 128, "metric": 0.3},
            {"qid": "q2", "selectivity": 0.1, "seed": 2026, "ef_search": 64, "metric": 0.2},
        ]
    )
    right = pd.DataFrame(
        [
            {"qid": "q1", "selectivity": 0.1, "seed": 2026, "ef_search": 64, "metric": 0.4},
            {"qid": "q1", "selectivity": 0.1, "seed": 2026, "ef_search": 128, "metric": 0.6},
            {"qid": "q3", "selectivity": 0.1, "seed": 2026, "ef_search": 64, "metric": 0.9},
        ]
    )
    diff = cs.paired_diff_frame(left, right, keys, "metric", direction="clustered_minus_random")
    assert set(diff["qid"]) == {"q1"}
    assert sorted(diff["ef_search"].tolist()) == [64, 128]
    assert all(math.isclose(v, 0.3) for v in diff["diff"])
    assert set(diff["direction"]) == {"clustered_minus_random"}


def test_ndcg_does_not_drop_irrelevant_candidates() -> None:
    scores = np.zeros(10, dtype=np.float32)
    gains = np.zeros(10, dtype=np.float64)
    scores[3], scores[1], scores[2] = 1.0, 0.5, 0.4
    gains[1], gains[2] = 1.0, 1.0
    idcg = cs.idcg_from_gains(gains, k=2)
    ndcg = cs.ndcg_at_k(np.array([3, 1, 2]), scores, gains, idcg, k=2)
    # Correct top-2 by score includes irrelevant doc 3; dropping it would give nDCG=1.
    expected = (1.0 / math.log2(3)) / (1.0 + 1.0 / math.log2(3))
    assert math.isclose(ndcg, expected, rel_tol=1e-6)


def test_ndcg_tie_break_is_deterministic() -> None:
    scores = np.ones(10, dtype=np.float32)
    gains = np.zeros(10, dtype=np.float64)
    gains[2], gains[5] = 1.0, 1.0
    idcg = cs.idcg_from_gains(gains, k=2)
    # Equal scores must select docs 2 and 5 by ascending doc ID.
    ndcg = cs.ndcg_at_k(np.array([5, 2, 9]), scores, gains, idcg, k=2)
    assert math.isclose(ndcg, 1.0, rel_tol=1e-12)


def test_ndcg_with_no_relevant_qrels_is_zero_and_full_prefix_matches_full_candidate_set() -> None:
    scores = np.linspace(0.1, 1.0, 10).astype(np.float32)
    empty_gains = np.zeros(10, dtype=np.float64)
    assert cs.ndcg_at_k(np.arange(10), scores, empty_gains, 0.0, k=10) == 0.0

    gains = np.zeros(10, dtype=np.float64)
    gains[[1, 4, 8]] = 1.0
    idcg = cs.idcg_from_gains(gains, k=10)
    full = np.arange(10)
    assert cs.ndcg_at_k(full, scores, gains, idcg, k=10) == cs.ndcg_at_k(full.copy(), scores, gains, idcg, k=10)


def test_three_center_farthest_first_is_reproducible() -> None:
    rng = np.random.default_rng(7)
    corpus = rng.normal(size=(80, 4)).astype(np.float32)
    corpus /= np.linalg.norm(corpus, axis=1, keepdims=True)
    m1, meta1 = rcm.build_three_center_mask(corpus, 13, 2026)
    m2, meta2 = rcm.build_three_center_mask(corpus, 13, 2026)
    assert np.array_equal(m1, m2)
    assert meta1["centers"] == meta2["centers"]
    assert int(m1.sum()) == 13


def test_three_center_mask_cardinality_uses_ceiling() -> None:
    rng = np.random.default_rng(11)
    corpus = rng.normal(size=(101, 3)).astype(np.float32)
    corpus /= np.linalg.norm(corpus, axis=1, keepdims=True)
    for rho in (0.01, 0.10, 0.30):
        target = math.ceil(rho * corpus.shape[0])
        mask, _ = rcm.build_three_center_mask(corpus, target, 2027)
        assert int(mask.sum()) == target


def test_original_mask_and_trace_hashes_unchanged() -> None:
    hashes = cs.load_input_hashes()
    assert len(hashes) >= 39
    for rel, digest in hashes.items():
        assert cs.sha256_file(ROOT / rel) == digest, rel
    assert (ROOT / "results" / "exp10b2" / "oracle_reachability.csv").exists()
    assert (ROOT / "results" / "exp10b2" / "ndcg_corrected.csv").exists()
