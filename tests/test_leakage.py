from pa_vfann.leakage import normalized_edit_distance, set_leakage, trace_leakage


def test_set_leakage_empty_sets_are_zero():
    assert set_leakage([], []) == 0.0
    assert set_leakage([1, 2], [1, 2]) == 0.0
    assert abs(set_leakage([1, 2], [3, 4]) - 1.0) < 1e-12
    assert abs(set_leakage([1, 2], [2, 3]) - 2.0 / 3.0) < 1e-12


def test_normalized_edit_distance():
    assert normalized_edit_distance([1, 2, 3], [1, 2, 3]) == 0.0
    assert normalized_edit_distance([], []) == 0.0
    assert normalized_edit_distance([1, 2, 3], []) == 1.0
    assert abs(normalized_edit_distance([1, 2, 3], [1, 9, 3]) - 1.0 / 3.0) < 1e-12


def test_leakage_channels_are_separate():
    result = trace_leakage([1, 2, 3], [1, 2, 4], 3, 2, [7, 8], [7])
    assert 0.0 < result["L_set"] < 1.0
    assert 0.0 < result["L_seq"] <= 1.0
    assert result["stop_position_delta"] == 1
    assert result["returned_count_delta"] == 1
    assert "L_output_ids" in result
