"""Tests for H1.3 prefix-constraint inference audit."""

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
    PrefixConstraint,
    assess_label_determination,
    assess_substantial_gain,
    assert_sound_labels,
    infer_from_constraints,
    public_constraints,
    score_labels,
)


def test_public_constraints_cover_all_three_stop_regimes():
    path = tuple(range(8))
    constraints, terminal = public_constraints(
        [path, path, path],
        [3, 5, 8],
        n=8,
        k=2,
        min_visits=3,
        max_budget=8,
    )
    sources = [c.source for c in constraints]
    assert terminal == [4]
    assert sources == [
        "q0:tau_eq_m", "q1:prefix_eq", "q1:terminal", "q2:tau_eq_B"
    ]
    assert constraints[0].lower == 2 and constraints[0].upper == 8
    assert constraints[1].lower == 1 and constraints[1].upper == 1
    assert constraints[2].lower == 1 and constraints[2].upper == 1
    assert constraints[3].lower == 0 and constraints[3].upper == 1


def test_attack_function_has_no_acl_parameter():
    params = set(inspect.signature(infer_from_constraints).parameters)
    assert params == {"n", "constraints", "authorized_count"}


def test_lower_bound_constraint_forces_all_unknown_nodes_authorized():
    constraints = [PrefixConstraint(np.array([0, 1]), 2, 2, "lower")]
    auth, unauth = infer_from_constraints(3, constraints)
    assert auth.tolist() == [True, True, False]
    assert unauth.tolist() == [False, False, False]


def test_upper_bound_constraint_forces_all_unknown_nodes_unauthorized():
    constraints = [PrefixConstraint(np.array([0, 1]), 0, 0, "upper")]
    auth, unauth = infer_from_constraints(3, constraints)
    assert auth.tolist() == [False, False, False]
    assert unauth.tolist() == [True, True, False]


def test_equality_constraint_uses_known_member_to_label_remaining_node():
    constraints = [
        PrefixConstraint(np.array([0]), 1, 1, "known"),
        PrefixConstraint(np.array([0, 1]), 1, 1, "equality"),
    ]
    auth, unauth = infer_from_constraints(3, constraints)
    assert auth.tolist() == [True, False, False]
    assert unauth.tolist() == [False, True, False]


def test_soundness_check_rejects_false_authorized_and_unauthorized_labels():
    with pytest.raises(RuntimeError, match="false authorized"):
        assert_sound_labels({0}, set(), {1}, 2)
    with pytest.raises(RuntimeError, match="false unauthorized"):
        assert_sound_labels(set(), {1}, {0, 1}, 2)


def test_score_labels_reports_new_members_and_recall_gain():
    score = score_labels(
        predicted_auth={0, 1},
        predicted_unauth={3},
        true_auth={0, 1, 2},
        n=6,
        terminal_auth={0},
    )
    assert score["new_authorized_nodes"] == 1
    assert score["new_authorized_tp"] == 1
    assert score["auth_recall"] == pytest.approx(2 / 3)
    assert score["terminal_auth_recall"] == pytest.approx(1 / 3)
    assert score["relative_recall_gain"] == pytest.approx(1.0)
    assert score["unauth_tp"] == 1
    assert score["unauth_fp"] == 0
    assert score["determined_fraction"] == pytest.approx(3 / 6)


def test_secondary_label_determination_is_excluded_from_escalation_gate():
    summary = pd.DataFrame(
        [
            {
                "policy_type": "random", "selectivity_pct": 1,
                "variant": "terminal_only", "mean_determined_fraction": 0.005,
                "mean_new_unauthorized_nodes": 0.0, "mean_unauth_precision": None,
            },
            {
                "policy_type": "random", "selectivity_pct": 1,
                "variant": "prefix_no_size", "mean_determined_fraction": 0.455,
                "mean_new_unauthorized_nodes": 4476.0, "mean_unauth_precision": 1.0,
            },
        ]
    )
    observation = assess_label_determination(summary)
    assert observation["in_escalation_gate"] is False
    assert observation["max_determined_fraction_gain"] == pytest.approx(0.45)


def test_pre_registered_gate_does_not_escalate_below_thresholds():
    base = {
        "variant": "prefix_no_size",
        "mean_new_authorized_nodes": 5.0,
        "new_authorized_acl_fraction": 0.5,
        "mean_relative_recall_gain": 0.1,
    }
    reached = assess_substantial_gain(pd.DataFrame([base]))
    assert reached["substantial_gain_reached"] is True
    below = dict(base, mean_new_authorized_nodes=4.9)
    stopped = assess_substantial_gain(pd.DataFrame([below]))
    assert stopped["substantial_gain_reached"] is False
    assert stopped["decision"] == "STOP_NO_ESCALATION"
