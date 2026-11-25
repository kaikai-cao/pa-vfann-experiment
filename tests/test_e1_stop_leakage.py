"""Tests for H1.1 E1 stop-boundary leakage audit.

The attack function must be ACL-free by construction; these tests also guard
the boundary cases (tau=m, tau=B) and the lemma's prefix-count identity.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from experiments.analyze_e1_stop_leakage import (  # noqa: E402
    MAX_BUDGET,
    MIN_VISITS,
    TOP_K,
    evaluate_inference,
    infer_last_node,
    prefix_hash,
    random_baselines,
    recompute_stop_position,
)


def test_tau_at_min_visits_yields_no_inference():
    # tau=m: the min-visit floor can force a stop before the last node is
    # authorized; the attack must NOT emit a positive label.
    path = tuple(range(100))
    assert infer_last_node(path, MIN_VISITS) is None


def test_tau_inside_window_returns_last_visited_node():
    path = (3, 7, 11, 19, 23, 31, 47)
    assert infer_last_node(path, 4, min_visits=2, max_budget=100) == 19
    assert infer_last_node(path, 7, min_visits=2, max_budget=100) == 47


def test_tau_at_budget_yields_no_inference():
    path = tuple(range(MAX_BUDGET))
    assert infer_last_node(path, MAX_BUDGET) is None


def test_lemma_last_node_authorized_and_prefix_has_k_minus_one():
    # Construct a path where positions m+1..m+K are the first K authorized
    # nodes; tau=m+K falls strictly inside (m, B).
    k = TOP_K
    path = list(range(100))
    mask = [False] * 100
    for i in range(MIN_VISITS + 1, MIN_VISITS + k + 1):
        mask[path[i - 1]] = True
    tau = MIN_VISITS + k
    assert 20 < tau < MAX_BUDGET
    inferred = infer_last_node(path, tau)
    verdict = evaluate_inference(path, tau, mask, inferred, k)
    assert inferred == path[tau - 1]
    assert verdict["inferred_authorized"] is True
    assert verdict["prefix_count"] == k - 1
    assert verdict["lemma_holds"] is True
    assert recompute_stop_position(path, mask, k, MIN_VISITS) == tau


def test_attack_signature_has_no_acl_parameter():
    # Structural guard: the attack must be unable to receive an ACL mask.
    params = set(inspect.signature(infer_last_node).parameters)
    assert params == {"public_path", "tau", "min_visits", "max_budget"}


def test_prefix_hash_matches_exp_common_formula():
    path = [12, 7, 99]
    expected = hashlib.sha256(",".join(str(v) for v in path).encode("ascii")).hexdigest()[:16]
    assert prefix_hash(path, len(path)) == expected
    assert prefix_hash([1, 2, 3, 4, 5], 3) == hashlib.sha256(b"1,2,3").hexdigest()[:16]


def test_out_of_range_tau_returns_none():
    path = (1, 2, 3)
    assert infer_last_node(path, 2, min_visits=2, max_budget=100) is None  # tau == m
    assert infer_last_node(path, 5, min_visits=2, max_budget=100) is None  # tau > len(path)
    assert infer_last_node(path, 0, min_visits=2, max_budget=100) is None


def test_evaluator_reports_none_for_uninformative_boundary():
    verdict = evaluate_inference((1, 2, 3), MIN_VISITS, [False] * 3, None)
    assert verdict == {"inferred_authorized": None, "prefix_count": None, "lemma_holds": None}


def test_random_baselines_use_distinct_precision_and_coverage_denominators():
    baselines = random_baselines(u=53, m=100, n=10000)
    assert baselines["random_precision_baseline"] == pytest.approx(0.01)
    assert baselines["random_coverage_baseline"] == pytest.approx(0.0053)


def test_coverage_ratio_is_the_deterministic_inverse_selectivity():
    baselines = random_baselines(u=53, m=100, n=10000)
    deterministic_coverage = 53 / 100
    assert (
        deterministic_coverage / baselines["random_coverage_baseline"]
        == pytest.approx(100.0)
    )


@pytest.mark.parametrize(
    ("u", "m", "n", "expected_error"),
    [
        (-1, 100, 10000, ValueError),
        (10001, 100, 10000, ValueError),
        (53, 0, 10000, ValueError),
        (53, 10001, 10000, ValueError),
        (53, 100, 0, ValueError),
        (53.0, 100, 10000, TypeError),
        (53, 100.0, 10000, TypeError),
        (53, 100, 10000.0, TypeError),
        (True, 100, 10000, TypeError),
    ],
)
def test_random_baselines_reject_invalid_inputs(u, m, n, expected_error):
    with pytest.raises(expected_error):
        random_baselines(u=u, m=m, n=n)
