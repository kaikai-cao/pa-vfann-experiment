"""Tests for H1.4 prior-aware negative membership evaluation."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from experiments.run_h1_3_prefix_constraint_inference import (  # noqa: E402
    infer_from_constraints,
)
from experiments.run_h1_4_prior_aware_evaluation import (  # noqa: E402
    BA_GAIN_THRESHOLD,
    BOOTSTRAP_REPS,
    METHODS,
    assess_upgrade_gate,
    b1_predict,
    b1_seed,
    b2_predict,
    cell_bootstrap_seed,
    hypergeometric_expected_fp,
    hypergeometric_zero_fp_probability,
    paired_bootstrap_mean_ci,
    path_frequency_order,
    score_negative_labels,
)


# --------------------------------------------------------------------------- #
# Baseline construction                                                        #
# --------------------------------------------------------------------------- #
def test_b2_ranking_counts_visits_and_breaks_ties_by_node_id():
    paths = [[0, 1, 2], [0, 1, 3], [5]]
    order, counts = path_frequency_order(paths, 6)
    assert counts.tolist() == [2, 2, 1, 1, 0, 1]
    # Node 0 and 1 tie at count 2; 2, 3 and 5 tie at count 1.
    assert order[:4].tolist() == [0, 1, 2, 3]
    assert set(order.tolist()) == set(range(6))
    assert b2_predict(order, 3).tolist() == [0, 1, 2]
    assert b2_predict(order, 0).size == 0


def test_b2_has_no_access_to_stop_position_acl_or_result_id():
    params = set(inspect.signature(path_frequency_order).parameters)
    assert params == {"paths", "n"}
    params = set(inspect.signature(b2_predict).parameters)
    assert params == {"order", "budget"}


def test_b1_is_reproducible_distinct_and_matched_budget():
    a = b1_predict(10, 4, b1_seed("random_01_00"))
    b = b1_predict(10, 4, b1_seed("random_01_00"))
    c = b1_predict(10, 4, b1_seed("random_01_01"))
    assert a.tolist() == b.tolist()
    assert len(set(a.tolist())) == 4
    assert a.tolist() != c.tolist()
    assert b1_predict(10, 0, 7).size == 0
    with pytest.raises(ValueError, match="B1 requires"):
        b1_predict(10, 11, 7)


def test_hypergeometric_analytic_values():
    assert hypergeometric_expected_fp(10000, 100, 53) == pytest.approx(0.53)
    # Small case with exact combinatorics: N=6, M=2, L=2 -> C(4,2)/C(6,2)=6/15.
    assert hypergeometric_zero_fp_probability(6, 2, 2) == pytest.approx(6 / 15)
    assert hypergeometric_zero_fp_probability(6, 2, 0) == 1.0
    assert hypergeometric_zero_fp_probability(6, 2, 5) == 0.0
    for fn in (hypergeometric_expected_fp, hypergeometric_zero_fp_probability):
        with pytest.raises(ValueError, match="out of range"):
            fn(10000, 10001, 5)
        with pytest.raises(ValueError, match="out of range"):
            fn(10000, 100, -1)


def test_attack_function_signature_has_no_acl():
    assert set(inspect.signature(infer_from_constraints).parameters) == {
        "n", "constraints", "authorized_count"
    }


# --------------------------------------------------------------------------- #
# Independent scorer                                                           #
# --------------------------------------------------------------------------- #
def test_score_negative_labels_confusion_matrix_and_balanced_accuracy():
    # N=10, authorized={0,1}, predicted unauthorized={2,3,4,0}.
    score = score_negative_labels([2, 3, 4, 0], {0, 1}, 10)
    assert (score["predicted_L"], score["tp"], score["fp"], score["fn"], score["tn"]) == (
        4, 3, 1, 5, 1
    )
    assert score["precision"] == pytest.approx(3 / 4)
    assert score["recall"] == pytest.approx(3 / 8)
    assert score["fpr"] == pytest.approx(1 / 2)
    assert score["specificity"] == pytest.approx(1 / 2)
    assert score["balanced_accuracy"] == pytest.approx((3 / 8 + 1 / 2) / 2)


def test_all_negative_baseline_has_balanced_accuracy_exactly_half():
    for n, m in ((100, 1), (10000, 100), (10000, 3000)):
        score = score_negative_labels(range(n), set(range(m)), n)
        assert score["recall"] == pytest.approx(1.0)
        assert score["specificity"] == pytest.approx(0.0)
        assert score["fpr"] == pytest.approx(1.0)
        assert score["balanced_accuracy"] == pytest.approx(0.5)


def test_zero_budget_score_is_well_defined():
    score = score_negative_labels([], {0, 1}, 10)
    assert score["precision"] is None
    assert score["recall"] == 0.0
    assert score["fpr"] == 0.0
    assert score["specificity"] == 1.0
    assert score["balanced_accuracy"] == pytest.approx(0.5)


def test_score_rejects_duplicate_and_out_of_range_predictions():
    with pytest.raises(ValueError, match="distinct"):
        score_negative_labels([1, 1], {0}, 10)
    with pytest.raises(ValueError, match="outside"):
        score_negative_labels([10], {0}, 10)
    with pytest.raises(ValueError, match="proper subset"):
        score_negative_labels([1], set(range(10)), 10)


# --------------------------------------------------------------------------- #
# Paired ACL-level bootstrap                                                   #
# --------------------------------------------------------------------------- #
def test_paired_bootstrap_resamples_acl_units_and_is_reproducible():
    diffs = np.arange(30, dtype=float) / 30.0
    seed = cell_bootstrap_seed("random", 1)
    r1 = np.random.default_rng(np.random.SeedSequence([seed, 0, 0x48314254]))
    r2 = np.random.default_rng(np.random.SeedSequence([seed, 0, 0x48314254]))
    first = paired_bootstrap_mean_ci(diffs, r1, reps=200)
    second = paired_bootstrap_mean_ci(diffs, r2, reps=200)
    assert first == second
    assert first[0] == pytest.approx(float(diffs.mean()))
    assert first[1] <= first[0] <= first[2]
    with pytest.raises(ValueError, match="non-empty"):
        paired_bootstrap_mean_ci([], r1, reps=10)


def test_bootstrap_defaults_are_pre_registered():
    assert BOOTSTRAP_REPS == 5000
    assert set(METHODS) == {
        "h1_3_prefix", "b0_all_negative",
        "b1_matched_random", "b2_path_frequency",
    }


# --------------------------------------------------------------------------- #
# Decision gate                                                                #
# --------------------------------------------------------------------------- #
def _summary_row(method: str, ba: float, ci_low: float, fp: int) -> dict[str, object]:
    return {
        "policy_type": "random",
        "selectivity_pct": 1,
        "method": method,
        "mean_balanced_accuracy": ba,
        "delta_ba_vs_b2_ci_low": ci_low,
        "delta_ba_vs_b2_ci_high": ci_low + 0.2,
        "delta_ba_vs_b1_ci_low": ci_low,
        "delta_ba_vs_b1_ci_high": ci_low + 0.2,
        "h1_3_fp_total": fp,
    }


def test_upgrade_gate_requires_all_five_conditions():
    good = pd.DataFrame(
        [
            _summary_row("h1_3_prefix", 0.75, 0.04, 0),
            _summary_row("b1_matched_random", 0.52, -0.01, 0),
            _summary_row("b2_path_frequency", 0.55, 0.0, 0),
        ]
    )
    passed = assess_upgrade_gate(good)
    assert passed["decision"] == "CANDIDATE_NEGATIVE_MEMBERSHIP_LEAKAGE"
    assert all(passed["checks"].values())

    below_threshold = good.copy()
    below_threshold.loc[0, "mean_balanced_accuracy"] = 0.59
    failed = assess_upgrade_gate(below_threshold)
    assert failed["decision"] == "STOP_NEGATIVE_EXTENSION"
    assert failed["checks"]["mean_ba_gain_vs_b2_at_least_0_05"] is False

    ci_not_positive = good.copy()
    ci_not_positive.loc[0, "delta_ba_vs_b2_ci_low"] = 0.0
    assert assess_upgrade_gate(ci_not_positive)["decision"] == "STOP_NEGATIVE_EXTENSION"

    has_fp = good.copy()
    has_fp.loc[0, "h1_3_fp_total"] = 1
    assert assess_upgrade_gate(has_fp)["decision"] == "STOP_NEGATIVE_EXTENSION"
    assert BA_GAIN_THRESHOLD == 0.05


def test_upgrade_gate_only_uses_primary_cell():
    rows = [
        _summary_row("h1_3_prefix", 0.75, 0.04, 0),
        _summary_row("b1_matched_random", 0.52, -0.01, 0),
        _summary_row("b2_path_frequency", 0.55, 0.0, 0),
    ]
    other = _summary_row("h1_3_prefix", 0.55, -0.2, 100)
    other["policy_type"] = "clustered"
    other["selectivity_pct"] = 30
    rows.append(other)
    result = assess_upgrade_gate(pd.DataFrame(rows))
    assert result["primary_cell"] == "random/1%"
    assert result["decision"] == "CANDIDATE_NEGATIVE_MEMBERSHIP_LEAKAGE"
