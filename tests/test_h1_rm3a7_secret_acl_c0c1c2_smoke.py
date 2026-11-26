"""H1-RM.3A.7 — private-ACL C0/C1/C2 smoke and observation-boundary tests.

No A0/A1 pair, no classifier, no BA/AUC, no attack advantage, no page trace.
The ACL fixtures are FIXED SYNTHETIC vectors written by the existing 3A.4
encode_acl_bitmap(); they are not experiment ACL instances.

Run:
    python -m pytest tests/test_h1_rm3a7_secret_acl_c0c1c2_smoke.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_3A4 = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
EXP_DIR = REPO_ROOT / "experiments" / "h1_rm_3a7_secret_acl_c0c1c2_smoke"
if str(MODULE_3A4) not in sys.path:
    sys.path.insert(0, str(MODULE_3A4))

import acl_bitmap as ab  # noqa: E402

N_MEMBERS = 200
K = 5
N_QUERIES = 6
GROUPS = ("C0", "C1", "C2")
BITS_A = [1 if i % 10 == 0 else 0 for i in range(N_MEMBERS)]
BITS_B = [1 if i % 10 != 0 else 0 for i in range(N_MEMBERS)]  # complement

RM2_INCLUDE = (
    REPO_ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib"
)

FORBIDDEN_OBS_KEYS = {
    "extra", "internal_id", "auth_hits", "khit_event_index", "n_filter_ok",
    "n_filter_check", "result_all_authorized",
}
FORBIDDEN_OBS_EVENTS = {"filter_check", "result_add", "result_remove"}


@pytest.fixture(scope="module")
def smoke_binary(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.fail("ENVIRONMENT BLOCK: no C++ compiler; cannot claim PASS.")
    build = tmp_path_factory.mktemp("h1acl_3a7_bin")
    exe = build / ("h1rm3a7_smoke.exe" if sys.platform == "win32"
                   else "h1rm3a7_smoke")
    proc = subprocess.run(
        [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
         "-DHNSWLIB_RM2_TRACE_ENABLED=1",
         f"-I{MODULE_3A4}", f"-I{EXP_DIR}", f"-I{RM2_INCLUDE}",
         str(EXP_DIR / "main.cpp"), "-o", str(exe)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"C++ compile failed:\n{proc.stdout}\n{proc.stderr}")
    return exe


def make_fixture(path, bits):
    blob = ab.encode_acl_bitmap(bits)
    assert ab.decode_acl_bitmap(blob) == bits
    path.write_bytes(blob)
    return path


def run_smoke(exe, fixture, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(exe), str(fixture), str(outdir)], capture_output=True, text=True
    )


def load_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def records_for(outdir, kind, group):
    path = outdir / f"{kind}_{group}.jsonl"
    assert path.is_file(), path
    rows = load_jsonl(path)
    notice = next(r for r in rows if r.get("record_type", "").endswith("notice"))
    events = [r for r in rows if "event_type" in r]
    summaries = [r for r in rows if r.get("record_type") == "group_summary"]
    return notice, events, summaries


def bit_of(label, bits):
    offset = label - 100000
    assert offset >= 0 and offset % 17 == 0
    idx = offset // 17
    assert 0 <= idx < len(bits)
    return bits[idx]


@pytest.fixture(scope="module")
def run_a(tmp_path_factory, smoke_binary):
    root = tmp_path_factory.mktemp("h1acl_3a7_a")
    fixture = make_fixture(root / "fixture_a.bin", BITS_A)
    out1, out2 = root / "run1", root / "run2"
    p1 = run_smoke(smoke_binary, fixture, out1)
    p2 = run_smoke(smoke_binary, fixture, out2)
    assert p1.returncode == 0, p1.stdout + p1.stderr
    assert "all_results_authorized=1" in p1.stdout
    assert "c2_khit_seen=1" in p1.stdout
    return root, fixture, out1, out2


def test_c0c1c2_results_and_khit_use_real_secret_acl(run_a):
    _, _, outdir, _ = run_a
    for group in GROUPS:
        notice, events, summaries = records_for(outdir, "internal_diagnostics", group)
        assert notice["attacker_observable"] is False
        assert len(summaries) == N_QUERIES
        for s in summaries:
            assert s["group"] == group
            assert s["result_all_authorized"] == 1
            assert s["returned_size"] > 0
        checks = [e for e in events if e["event_type"] == "filter_check"]
        for e in checks:
            assert e["extra"] == bit_of(e["external_id"], BITS_A)
        for s in summaries:
            same_query = [e for e in checks if e["query_id"] == s["query_id"]]
            authorized = [e for e in same_query if e["extra"] == 1]
            assert s["n_filter_check"] == len(same_query)
            assert s["n_filter_ok"] == len(authorized)
            assert s["auth_hits"] == len(authorized)  # per-query reset + count
    khit = [
        s for s in records_for(outdir, "internal_diagnostics", "C2")[2]
        if s["khit_event_index"] >= 0
    ]
    assert khit, "C2 K-hit stop was never exercised"
    assert all(s["auth_hits"] >= K for s in khit)


def test_observer_proxy_has_no_authorization_information(run_a):
    _, _, outdir, _ = run_a
    for group in GROUPS:
        notice, events, _ = records_for(outdir, "observer_proxy", group)
        assert notice["trust"] == "untrusted_observer_view"
        assert notice["trace_kind"] == "logical_observation_proxy"
        assert notice["is_physical_page_trace"] is False
        assert set(notice["filtered_internal_event_types"]) == FORBIDDEN_OBS_EVENTS
        assert events, "observer proxy must still be a usable logical proxy"
        for e in events:
            assert e["event_type"] not in FORBIDDEN_OBS_EVENTS
            assert not (FORBIDDEN_OBS_KEYS & set(e))
            if e["event_type"] != "distance_eval":
                assert "external_id" not in e
                assert "dist_bits" not in e
        # The proxy is not a dump of the authorized set: at least one observed
        # distance evaluation per query concerns an UNAUTHORIZED label.
        by_query = {}
        for e in events:
            if e["event_type"] == "distance_eval":
                by_query.setdefault(e["query_id"], []).append(e["external_id"])
        for q in range(N_QUERIES):
            labels = by_query.get(q, [])
            assert labels
            assert any(bit_of(label, BITS_A) == 0 for label in labels)


def test_layers_are_separate_and_order_preserved(run_a):
    _, _, outdir, _ = run_a
    for group in GROUPS:
        _, internal_events, _ = records_for(
            outdir, "internal_diagnostics", group)
        _, observer_events, _ = records_for(outdir, "observer_proxy", group)
        # event_index is scoped per query (the harness resets it each query).
        for q in range(N_QUERIES):
            internal_indices = [
                e["event_index"] for e in internal_events if e["query_id"] == q
            ]
            observer_indices = [
                e["event_index"] for e in observer_events if e["query_id"] == q
            ]
            assert observer_indices == sorted(observer_indices)
            assert set(observer_indices) <= set(internal_indices)
        # internal has directly-leaky events; observer deliberately does not.
        assert any(e["event_type"] == "filter_check" for e in internal_events)
        assert "extra" in internal_events[0]


def test_internal_authorization_change_does_not_enter_observer_proxy(
        tmp_path, smoke_binary, run_a):
    _, _, out_a, _ = run_a
    fixture_b = make_fixture(tmp_path / "fixture_b.bin", BITS_B)
    out_b = tmp_path / "run_b"
    proc = run_smoke(smoke_binary, fixture_b, out_b)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    def filter_decisions(outdir, group):
        _, events, _ = records_for(outdir, "internal_diagnostics", group)
        return {
            e["external_id"]: e["extra"]
            for e in events if e["event_type"] == "filter_check"
        }

    a_dec = filter_decisions(out_a, "C0")
    b_dec = filter_decisions(out_b, "C0")
    common = set(a_dec) & set(b_dec)
    assert common, "the two fixtures must exercise overlapping labels"
    assert any(a_dec[x] != b_dec[x] for x in common), \
        "fixtures must actually differ in authorization decisions"

    def observer_schema(outdir, group):
        _, events, _ = records_for(outdir, "observer_proxy", group)
        schema = {}
        for e in events:
            schema.setdefault(e["event_type"], set()).update(e)
        return schema

    schema_a = observer_schema(out_a, "C0")
    schema_b = observer_schema(out_b, "C0")
    # A different ACL may legitimately cause a NEW observable event TYPE to
    # occur (e.g. search_stop). What must not change is the field schema of
    # event types that do occur, and no authorization field may ever appear.
    for event_type in set(schema_a) & set(schema_b):
        assert schema_a[event_type] == schema_b[event_type]
    for fields in list(schema_a.values()) + list(schema_b.values()):
        assert not (FORBIDDEN_OBS_KEYS & fields)
        assert "extra" not in fields


def test_repeatable(run_a):
    _, _, out1, out2 = run_a
    for group in GROUPS:
        for kind in ("internal_diagnostics", "observer_proxy"):
            p1 = out1 / f"{kind}_{group}.jsonl"
            p2 = out2 / f"{kind}_{group}.jsonl"
            assert p1.read_bytes() == p2.read_bytes(), f"{kind}_{group}"
