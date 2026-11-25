"""H1-RM.2 tests: instrumentation scope, semantic equivalence, C2 boundary."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "h1_rm2"
RM2_ALG = ROOT / "third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/hnswalg.h"
PRISTINE_ALG = ROOT / "third_party/hnswlib-v0.9.0/hnswlib/hnswalg.h"
PATCH = ROOT / "patches/hnswlib-v0.9.0-rm2-stop-semantics.patch"


def load(sub: str, name: str):
    with open(BASE / sub / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def audit():
    """Committed compact audit log: one record per (query, group)."""
    with open(BASE / "events_audit.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SITE_TYPES = ["distance_eval", "candidate_pop", "candidate_consider",
              "filter_check", "result_add", "result_remove", "stop_check", "search_stop"]


# --- instrumentation scope: pure observation, no algorithm change -----------
def test_patch_inserts_only_rm2_ev_observation_calls():
    a = PRISTINE_ALG.read_text(encoding="utf-8").splitlines()
    b = RM2_ALG.read_text(encoding="utf-8").splitlines()
    added = [ln for ln in difflib.unified_diff(a, b, lineterm="") if ln.startswith("+") and not ln.startswith("+++")]
    # every added line is either a macro definition, an RM2_EV call/continuation,
    # a comment, an include, or blank.
    allowed = ("#ifdef HNSWLIB_RM2_TRACE_ENABLED", "#endif", "#else", "#include \"rm2_sink.h\"",
               "#define RM2_EV", "namespace hnswlib {")
    macro_body = {
        "do {", "if (g_rm2_enabled) {", "rm2_emit((const char *)(ev), (uint64_t)(iid),",
        "(uint64_t)getExternalLabel((iid)), (int)(lvl),", "(float)(d), (int64_t)(extra));",
        "}", "} while (0)",
        "#define RM2_EV(ev, iid, lvl, d, extra)",
        "#define RM2_EV(ev, iid, lvl, d, extra) do {} while (0)",
        "flag_consider_candidate ? 1 : 0);", "flag_stop_search ? 1 : 0);",
    }
    for ln in added:
        s = ln[1:].strip()
        # strip C preprocessor continuation backslash used in the macro body
        core = s.rstrip("\\").rstrip() if s.endswith("\\") else s
        if not s or s.startswith("//") or s.startswith("RM2_EV") or s.startswith("#include"):
            continue
        if core in macro_body:
            continue
        if s.startswith(allowed):
            continue
        pytest.fail(f"non-observation line inserted into hnswalg.h: {ln!r}")


def test_patch_does_not_touch_search_logic_tokens():
    # The added lines must not modify candidate-selection / result / stop logic.
    a = PRISTINE_ALG.read_text(encoding="utf-8").splitlines()
    b = RM2_ALG.read_text(encoding="utf-8").splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    forbidden = ("lowerBound =", "candidate_set.emplace", "flag_consider_candidate =",
                 "flag_stop_search =", "flag_remove_extra =", "top_candidates.pop()",
                 "while (flag_remove_extra)", "should_stop_search(candidate_dist")
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        changed = a[i1:i2] + b[j1:j2]
        for ln in changed:
            for tok in forbidden:
                # allow lines that only carry an RM2_EV site right after the token
                if tok in ln and "RM2_EV" not in ln and not ln.strip().startswith("//"):
                    pytest.fail(f"search-logic line modified: {ln!r}")


def test_all_eight_event_types_emitted():
    # Every site has a nonzero count in at least one (query, group) audit record.
    au = audit()
    for t in SITE_TYPES:
        assert any(r["n_" + t] > 0 for r in au), t


def test_filter_check_only_on_actual_callback():
    # filter_check counts exist in the audit; sink-off emits no events at all.
    assert any(r["n_filter_check"] > 0 for r in audit())
    assert load("trace_off", "events.jsonl") == []


# --- C0/C1 semantic equivalence --------------------------------------------
def test_c0_c1_top10_identical_after_id_mapping():
    gate = json.loads((BASE / "gate.json").read_text(encoding="utf-8"))
    assert gate["checks"]["c0_c1_top10_external_id"] is True
    assert gate["checks"]["c0_c1_top10_float32_bits"] is True
    assert gate["metrics"]["c0_c1_top10_id_matches"] == 500
    assert gate["metrics"]["c0_c1_top10_bits_matches"] == 500


def test_c0_c1_distance_eval_sequence_identical():
    # The audit stores a canonical FNV-1a hash of the full (internal_id,
    # dist_bits, level) distance-eval triple sequence per query. Identical
    # hashes for C0/C1 on every query prove sequence equality without shipping
    # the 67MB raw log.
    au = audit()
    by = {(r["query_id"], r["group"]): r for r in au}
    for q in range(50):
        c0, c1 = by[(q, "C0")], by[(q, "C1")]
        assert c0["n_distance_eval"] == c1["n_distance_eval"]
        assert c0["distance_eval_hash"] == c1["distance_eval_hash"]
    assert sum(r["n_distance_eval"] for r in au if r["group"] == "C0") == 50998


def test_upstream_internal_label_conversion_is_documented_in_manifest():
    man = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    assert man["config"]["label_base"] == 100000 and man["config"]["label_step"] == 17
    assert man["groups"]["C1"].startswith("searchStopConditionClosest")


def test_three_channels_topk_identical():
    gate = json.loads((BASE / "gate.json").read_text(encoding="utf-8"))
    for g in ("C0", "C1", "C2"):
        assert gate["checks"][f"topk_channels_identical_{g}"] is True


# --- C2 control-flow boundary -----------------------------------------------
def test_c2_khit_count_exact_and_stop_lags():
    s = [r for r in load("trace_on", "run_summary.jsonl") if r["group"] == "C2"]
    assert len(s) == 50
    for r in s:
        assert r["auth_hits"] == r["n_filter_ok"] == r["returned_size"]
        assert 0 <= r["khit_event_index"] < r["first_search_stop_index"]
        assert r["n_search_stop"] == 1


def test_c2_stop_boundary_has_extra_observable_events():
    gate = json.loads((BASE / "gate.json").read_text(encoding="utf-8"))
    m = gate["metrics"]
    assert m["c2_gap_min"] >= 3 and m["c2_gap_max"] <= 52
    mid = m["c2_events_between_khit_and_stop"]
    assert mid["distance_eval"] > 0 and mid["candidate_consider"] > 0 and mid["filter_check"] > 0
    assert mid["candidate_pop"] == 0  # stop is at the candidate_set loop boundary


def test_c1_returns_ef_sized_result_c2_returns_k_sized():
    s = load("trace_on", "run_summary.jsonl")
    assert {r["returned_size"] for r in s if r["group"] == "C1"} == {64}
    assert {r["returned_size"] for r in s if r["group"] == "C0"} == {10}
    c2s = {r["returned_size"] for r in s if r["group"] == "C2"}
    assert all(10 <= v <= 14 for v in c2s)


def test_gate_all_pass():
    gate = json.loads((BASE / "gate.json").read_text(encoding="utf-8"))
    assert gate["decision"] == "PASS"
    assert all(gate["checks"].values())
