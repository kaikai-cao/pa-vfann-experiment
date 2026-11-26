"""H1-RM.3A.8 — A0/A1 paired-ACL FEASIBILITY tests.

Feasibility only: no classifier, no BA/AUC, no attack advantage, no page or
physical trace simulation. A0/A1 are researcher-side counterfactuals.

Run:
    python -m pytest tests/test_h1_rm3a8_acl_pair_feasibility.py -v

All ACL blobs / traces / diagnostics live in pytest tmp_path. Nothing private
is written into the repository.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVER_DIR = REPO_ROOT / "experiments" / "h1_rm_3a8_acl_pair_feasibility"
MODULE_3A4 = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
for p in (DRIVER_DIR, MODULE_3A4):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import acl_bitmap as ab  # noqa: E402
import pair_driver as pd  # noqa: E402

GROUPS = pd.GROUPS


def _read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def _events(outdir, kind, group):
    return [r for r in _read_jsonl(outdir / f"{kind}_{group}.jsonl")
            if "event_type" in r]


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """Build one private pair, compile the harness once, run both ACLs once."""
    work = tmp_path_factory.mktemp("h1acl_3a8")
    private = work / "private"
    manifest = pd.build_pair(private)
    exe = pd.compile_harness(work / "harness")
    out0, out1 = work / "trace_A0", work / "trace_A1"
    r0 = pd.run_harness(exe, manifest.a0_path, out0)
    r1 = pd.run_harness(exe, manifest.a1_path, out1)
    report = pd.analyse_run(manifest, out0, out1, r0.stdout, r1.stdout)
    return {
        "work": work, "manifest": manifest, "exe": exe,
        "out0": out0, "out1": out1, "r0": r0, "r1": r1,
        "report": report, "loader_exe": work / "loader",
    }


# --------------------------------------------------------------------------- #
# A. Pairing integrity
# --------------------------------------------------------------------------- #
def test_target_preselection_precedes_acl_generation():
    # select_targets accepts ONLY public quantities (no ACL/bit/trace argument).
    params = list(inspect.signature(ab.select_targets).parameters)
    assert set(params) == {"n_members", "target_count", "public_seed"}
    assert "acl" not in params and "bitmap" not in params
    # Same public seed -> same target; deterministic and independent of any ACL.
    a = ab.select_targets(pd.N_MEMBERS, 1, pd.PUBLIC_SEED)
    b = ab.select_targets(pd.N_MEMBERS, 1, pd.PUBLIC_SEED)
    assert a == b and len(a) == 1
    assert 0 <= a[0] < pd.N_MEMBERS


def test_single_bit_pair_invariants(session):
    m = session["manifest"]
    assert m.n == pd.N_MEMBERS
    assert len(m.a0) == len(m.a1) == m.n
    assert m.diff == [m.target]
    assert ab.diff_indices(m.a0, m.a1) == [m.target]
    assert m.a0[m.target] == 0
    assert m.a1[m.target] == 1
    assert all(m.a0[i] == m.a1[i] for i in range(m.n) if i != m.target)
    assert m.target_label == pd.LABEL_BASE + pd.LABEL_STEP * m.target


def test_non_target_bits_are_identical_after_encoding(session):
    m = session["manifest"]
    b0 = ab.decode_acl_bitmap(m.a0_path.read_bytes())
    b1 = ab.decode_acl_bitmap(m.a1_path.read_bytes())
    assert b0 == m.a0 and b1 == m.a1
    assert ab.diff_indices(b0, b1) == [m.target]


def test_invalid_target_index_rejected():
    base = [1, 0, 1, 0]
    for bad in (-1, len(base), len(base) + 3):
        with pytest.raises(ValueError):
            ab.derive_target_pair(base, bad)


def test_cpp_python_fixture_interop(session):
    m = session["manifest"]
    # Query the target label plus a few non-target neighbours in both ACLs.
    neighbours = [m.target_label - pd.LABEL_STEP, m.target_label,
                  m.target_label + pd.LABEL_STEP]
    for fixture, bits, tag in ((m.a0_path, m.a0, "A0"),
                               (m.a1_path, m.a1, "A1")):
        got = pd.cpp_loader_bits(fixture, neighbours,
                                 session["work"] / f"loader_{tag}")
        assert got[m.target_label] == bits[m.target]
        for label in neighbours:
            idx = ab.label_to_index(label, pd.LABEL_BASE, pd.LABEL_STEP)
            assert got[label] == bits[idx]


# --------------------------------------------------------------------------- #
# B. Search runnability
# --------------------------------------------------------------------------- #
def test_both_acls_run_c0c1c2_with_authorized_results(session):
    assert session["r0"].returncode == 0, session["r0"].stdout + session["r0"].stderr
    assert session["r1"].returncode == 0, session["r1"].stdout + session["r1"].stderr
    for r in (session["r0"], session["r1"]):
        assert "all_results_authorized=1" in r.stdout
        assert "c2_khit_seen=1" in r.stdout
    sr = session["report"]["search_runnable"]
    assert sr["a0_all_results_authorized"] and sr["a1_all_results_authorized"]
    # K-hit triggering is REPORTED, never a hard admission condition.
    assert isinstance(sr["a0_c2_khit_seen"], bool)
    assert isinstance(sr["a1_c2_khit_seen"], bool)


def test_six_paired_group_outputs_complete(session):
    for group in GROUPS:
        for outdir in (session["out0"], session["out1"]):
            for kind in ("internal_diagnostics", "observer_proxy"):
                p = outdir / f"{kind}_{group}.jsonl"
                assert p.is_file(), p
            sums = [r for r in _read_jsonl(
                outdir / f"internal_diagnostics_{group}.jsonl")
                if r.get("record_type") == "group_summary"]
            assert len(sums) == pd.N_QUERIES
            assert all(s["group"] == group for s in sums)
            assert all(s["result_all_authorized"] == 1 for s in sums)


def test_filter_check_matches_bitmap_bit_for_bit(session):
    m = session["manifest"]
    for outdir, bits in ((session["out0"], m.a0), (session["out1"], m.a1)):
        for group in GROUPS:
            for e in _events(outdir, "internal_diagnostics", group):
                if e["event_type"] == "filter_check":
                    idx = ab.label_to_index(e["external_id"],
                                            pd.LABEL_BASE, pd.LABEL_STEP)
                    assert e["extra"] == bits[idx]


def test_observer_never_carries_internal_diagnostics(session):
    forbidden_keys = {"extra", "internal_id", "auth_hits", "khit_event_index",
                      "n_filter_ok", "n_filter_check", "result_all_authorized"}
    forbidden_events = {"filter_check", "result_add", "result_remove"}
    for group in GROUPS:
        for outdir in (session["out0"], session["out1"]):
            notice = next(r for r in _read_jsonl(
                outdir / f"observer_proxy_{group}.jsonl")
                if r.get("record_type", "").endswith("notice"))
            assert notice["is_physical_page_trace"] is False
            assert set(notice["filtered_internal_event_types"]) == forbidden_events
            for e in _events(outdir, "observer_proxy", group):
                assert e["event_type"] not in forbidden_events
                assert not (forbidden_keys & set(e))


# --------------------------------------------------------------------------- #
# C. Target observation — three INDEPENDENT conditions, reported faithfully.
#    No unconditional "target must appear in all six traces" admission.
# --------------------------------------------------------------------------- #
def test_target_visibility_report_is_faithful(session):
    m = session["manifest"]
    vis = session["report"]["target_visibility"]
    assert len(vis) == len(GROUPS) * 2
    seen = {(v["acl"], v["group"]): v for v in vis}
    for group in GROUPS:
        for acl, outdir, bits in (("A0", session["out0"], m.a0),
                                  ("A1", session["out1"], m.a1)):
            v = seen[(acl, group)]
            int_ev = _events(outdir, "internal_diagnostics", group)
            obs_ev = _events(outdir, "observer_proxy", group)
            assert v["internal_distance_eval"] == any(
                e["event_type"] == "distance_eval"
                and e.get("external_id") == m.target_label for e in int_ev)
            assert v["internal_filter_check"] == any(
                e["event_type"] == "filter_check"
                and e.get("external_id") == m.target_label for e in int_ev)
            assert v["observer_visible"] == any(
                e.get("external_id") == m.target_label for e in obs_ev)
    # The three booleans are genuinely separate fields, not aliased.
    assert all(set(("internal_distance_eval", "internal_filter_check",
                    "observer_visible")) <= set(v) for v in vis)


def test_observer_visible_label_does_not_encode_authorization(session):
    # Even when the target is observer-visible in BOTH ACLs, the proxy carries
    # no authorization bit. The same external_id must appear with identical
    # field schema in A0 and A1.
    m = session["manifest"]
    for group in GROUPS:
        schema = {}
        for outdir in (session["out0"], session["out1"]):
            for e in _events(outdir, "observer_proxy", group):
                if e.get("external_id") == m.target_label:
                    schema.setdefault(e["event_type"], set()).update(e.keys())
        for fields in schema.values():
            assert not ({"extra", "auth_hits", "result_all_authorized"} & fields)


# --------------------------------------------------------------------------- #
# D. Trace pairing — sensitivity evidence only, not a leakage claim.
# --------------------------------------------------------------------------- #
def test_trace_comparison_report_is_faithful(session):
    comps = {c["group"]: c for c in session["report"]["trace_comparison"]}
    assert set(comps) == set(GROUPS)
    for group in GROUPS:
        c = comps[group]
        e0 = _events(session["out0"], "observer_proxy", group)
        e1 = _events(session["out1"], "observer_proxy", group)
        assert c["a0_event_count"] == len(e0)
        assert c["a1_event_count"] == len(e1)
        assert c["content_equal"] == (e0 == e1)
        assert c["schemas_equal"] is True  # R1 schema is identical by contract
        # No difference report is fabricated when the traces are equal.
        if e0 == e1:
            assert c["first_difference"] is None
        else:
            assert c["first_difference"] is not None


def test_repeatable_with_same_paired_fixture(session):
    m, exe = session["manifest"], session["exe"]
    work = session["work"]
    for tag, fixture, out in (("r_A0", m.a0_path, work / "repeat_A0"),
                              ("r_A1", m.a1_path, work / "repeat_A1")):
        proc = pd.run_harness(exe, fixture, out)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    for group in GROUPS:
        for kind in ("internal_diagnostics", "observer_proxy"):
            p0 = session["out0"] / f"{kind}_{group}.jsonl"
            p1 = session["out1"] / f"{kind}_{group}.jsonl"
            q0 = (work / "repeat_A0") / f"{kind}_{group}.jsonl"
            q1 = (work / "repeat_A1") / f"{kind}_{group}.jsonl"
            assert p0.read_bytes() == q0.read_bytes(), f"A0 {kind}_{group}"
            assert p1.read_bytes() == q1.read_bytes(), f"A1 {kind}_{group}"


# --------------------------------------------------------------------------- #
# Repository hygiene
# --------------------------------------------------------------------------- #
def test_private_artifacts_not_in_repository(session):
    # No ACL blob, private manifest, trace or diagnostic is inside the repo.
    for pattern in ("acl_A0.bin", "acl_A1.bin", "report.json", "private",
                    "trace_A0", "trace_A1"):
        matches = list(REPO_ROOT.rglob(pattern))
        assert not matches, f"private artifact leaked into repo: {matches[:2]}"
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True, text=True,
    ).stdout.splitlines()
    assert not any("acl_A0" in f or "acl_A1" in f for f in tracked)
