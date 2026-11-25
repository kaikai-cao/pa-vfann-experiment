"""EXP-10A Phase 0 minimal automated checks.

These tests consume committed raw outputs; they do not recompile C++.
Run the harness first via build.ps1 / run_probe.ps1 and exp10a_validate.py.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"


def _load(name):
    with (RAW / name).open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_validation_verdict_pass():
    v = json.loads((RAW / "exp10a_validation.json").read_text(encoding="utf-8"))
    assert v["verdict"] == "PASS"
    for key in ("V1", "V2", "V3", "V4", "V5"):
        assert v[key]["pass"], (key, v[key]["errors"])


def test_event_count_equals_independent_counter():
    primary = [r for r in _load("exp10a_probe_summary.jsonl") if r.get("record") == "primary"]
    assert len(primary) == 50
    for row in primary:
        assert row["event_count"] == row["distance_call_count"] > 0
        assert row["has_level0"] is True
        assert row["has_upper"] is True
        assert row["sinkoff_event_count"] == 0


def test_topk_bit_exact_across_three_runs():
    names = (
        "exp10a_upstream_topk.jsonl",
        "exp10a_instrumented_topk.jsonl",
        "exp10a_sinkoff_topk.jsonl",
    )
    keysets = [
        [
            (r["query_id"], r["rank"], r["external_id"], r["dist_bits"])
            for r in _load(name)
        ]
        for name in names
    ]
    assert len(keysets[0]) == 500
    assert keysets[0] == keysets[1] == keysets[2]


def test_trace_hash_reproducible():
    primary = [r for r in _load("exp10a_probe_summary.jsonl") if r.get("record") == "primary"]
    rebuilt = {r["query_id"]: r["rebuilt_trace_hash"] for r in _load("exp10a_probe_summary.jsonl")
               if r.get("record") == "rebuilt"}
    for row in primary:
        assert row["trace_hash"] == row["repeat_trace_hash"]
        assert row["trace_hash"] == rebuilt[row["query_id"]]


def test_patch_contains_exactly_four_trace_sites():
    patch = (ROOT / "patches" / "hnswlib-v0.9.0-query-trace.patch").read_text(encoding="utf-8")
    sites = [
        line for line in patch.splitlines()
        if line.startswith("+") and "HNSW_TRACE_SITE(" in line and "#define" not in line
    ]
    assert len(sites) == 4
    for site in ("entrypoint", "upper_layer_neighbor", "level0_entrypoint", "level0_neighbor"):
        assert any(f'"{site}"' in line for line in sites)
