"""Tests 1 and 2: output-ID observer attribution."""

from __future__ import annotations

from pa_vfann_exp02a.observers import (
    output_id_observers, reclassify_leakage_row, visibility_matrix,
)

E3 = "E3_FIXED_TRACE"
E1 = "E1_POSTFILTER"


def test_1_local_client_filter_does_not_expose_topk_to_server():
    vis = visibility_matrix(E3, "B", feedback_ids=False, network_tls=True)
    assert vis["O_server"]["topk_ids"] is False
    assert output_id_observers(E3, False) == ("O_client",)

    row = {
        "output_id_leakage": 0.97,
        "discovery_leakage": 0.0, "visit_leakage": 0.0,
        "expansion_leakage": 0.0, "visit_edit_leakage": 0.0,
        "stop_position_delta": 0, "candidate_count_delta": 0,
        "stop_position": 500, "candidate_count": 4000,
    }
    new = reclassify_leakage_row(row, E3, False)
    assert new["server_can_observe_topk_ids"] == 0
    assert new["cross_policy_output_distinguishability"] == 0.97
    # Legacy metric is retained numerically but attributed to the client.
    assert new["output_id_observers"] == "O_client"
    assert new["server_observable_leakage"] == 0.0


def test_2_feedback_makes_topk_visible_to_server_output_observer():
    vis = visibility_matrix(E3, "B", feedback_ids=True, network_tls=True)
    assert vis["O_server"]["topk_ids"] is True
    assert "O_server" in output_id_observers(E3, True)

    row = {
        "output_id_leakage": 0.97,
        "discovery_leakage": 0.0, "visit_leakage": 0.0,
        "expansion_leakage": 0.0, "visit_edit_leakage": 0.0,
        "stop_position_delta": 0, "candidate_count_delta": 0,
        "stop_position": 500, "candidate_count": 4000,
    }
    new = reclassify_leakage_row(row, E3, True)
    assert new["server_can_observe_topk_ids"] == 1
    assert new["server_observable_leakage"] == 0.97

    # E1/E2 produce the result at the server even without explicit feedback.
    new_e1 = reclassify_leakage_row(row, E1, False)
    assert new_e1["server_can_observe_topk_ids"] == 1
    assert "O_server" in new_e1["output_id_observers"]
