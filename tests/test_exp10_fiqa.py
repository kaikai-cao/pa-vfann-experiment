import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_config_recall_gate_written_before_baseline() -> None:
    cfg = load_json("experiments/exp10_fiqa_hnswlib/experiment_config.json")
    gate = cfg["recall_gate"]
    assert gate["written_before_viewing_baseline"] is True
    assert gate["rule"] == "STOP_ORACLE_ONLY_IF_ALL_EFSEARCH_MEAN_UNFILTERED_EXACT_RECALL10_BELOW_0_90"
    assert gate["ef_search_values"] == [64, 128, 256]


def test_data_gate_keeps_original_zip_md5_unverified() -> None:
    data = load_json("data/exp10_fiqa_manifest.json")
    assert data["data_gate"] == "PASS_COMPONENT_ARTIFACTS"
    assert data["original_zip_md5"]["status"] == "NOT_VERIFIED"
    assert data["counts"] == {
        "corpus": 57638,
        "queries_all_splits": 6648,
        "queries_test": 648,
        "qrels_pairs": 1706,
    }


def test_smoke_validation_passes() -> None:
    smoke = load_json("results/raw/exp10_fiqa_smoke/exp10_fiqa_smoke_validation.json")
    assert smoke["verdict"] == "PASS"
    assert smoke["event_count_equals_independent_counter"] is True
    assert smoke["sinkoff_topk_bit_exact"] is True
    assert smoke["repeat_trace_hash_equal"] is True
    assert smoke["rebuilt_trace_hash_equal"] is True


def test_summary_rows_have_counter_equality_and_gate() -> None:
    summary_path = ROOT / "results/raw/exp10_fiqa_probe_summary.jsonl"
    rows = [json.loads(line) for line in summary_path.open(encoding="utf-8") if line.strip()]
    assert len(rows) == 3 * 648
    assert all(r["event_count"] == r["distance_call_count"] for r in rows)
    assert {r["ef_search"] for r in rows} == {64, 128, 256}
    gate = load_json("results/exp10_fiqa_recall_gate.json")
    assert set(gate["mean_unfiltered_recall10"]) == {"64", "128", "256"}
    assert gate["all_below_threshold"] == (gate["oracle_main_conclusion"] == "STOP")


def test_exact_ground_truth_shape() -> None:
    gt = load_json("data/exp10_fiqa_embeddings/gt_unfiltered.json")
    assert len(gt["query_ids"]) == 648
    assert len(gt["topk"]) == 648
    assert all(len(row) == 10 for row in gt["topk"])
    assert all("boundary_score" in row and "tie_count" in row for row in gt["boundary"][:10])


def test_bootstrap_confidence_intervals_are_ordered() -> None:
    df = pd.read_csv(ROOT / "results/exp10_fiqa_bootstrap.csv")
    assert not df.empty
    assert (df["ci_low"] <= df["ci_high"]).all()
    assert (df["n_queries"] > 0).all()


def test_compressed_trace_manifest_complete() -> None:
    man = load_json("results/raw/exp10_fiqa_trace_manifest.json")
    assert len(man["artifacts"]) == 4
    for rec in man["artifacts"].values():
        assert rec["raw_size_bytes"] > 0
        assert rec["compressed_size_bytes"] > 0
        assert len(rec["raw_sha256"]) == 64
        assert len(rec["compressed_sha256"]) == 64


def test_report_records_zip_md5_boundary() -> None:
    report = (ROOT / "docs/EXP10_FIQA_REPORT.md").read_text(encoding="utf-8")
    assert "NOT_VERIFIED" in report
    assert "三个都低于 0.90" in report
    assert "HNSW query distance-evaluation trace" in report
