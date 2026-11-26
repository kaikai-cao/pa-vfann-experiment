"""H1-RM.3A.6 — real HNSW search integration (correctness only).

No C0/C1/C2, no A0/A1 pair, no trace simulation, no classifier, no attack
metric. The ACL fixture is a FIXED SYNTHETIC vector written by the existing
3A.4 encode_acl_bitmap(); it is not an experiment ACL instance.

Run:
    python -m pytest tests/test_h1_rm3a6_search_integration.py -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_3A4 = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
EXP_DIR = REPO_ROOT / "experiments" / "h1_rm_3a6_search_integration"
if str(MODULE_3A4) not in sys.path:
    sys.path.insert(0, str(MODULE_3A4))

import acl_bitmap as ab  # noqa: E402

FIXTURE_BITS = [1] * 16 + [0] * 48  # fixed non-real vector, N = 64
N_MEMBERS = len(FIXTURE_BITS)
K = 5

HNSW_INCLUDE_DIRS = {
    "pristine": REPO_ROOT / "third_party" / "hnswlib-v0.9.0" / "hnswlib",
    "rm2": REPO_ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib",
}

REQUIRED_CHECKS = {
    "unfiltered_has_unauthorized",
    "filtered_nonempty",
    "filtered_all_authorized",
    "filtered_outside_unfiltered_topk",
    "callback_invocations_positive",
    "counting_run_all_authorized",
}


@pytest.fixture(scope="module")
def acl_fixture(tmp_path_factory):
    # Uses the SAME encoder as 3A.4/3A.5; no second binary format is invented.
    path = tmp_path_factory.mktemp("h1acl_3a6") / "fixed_test_vector.bin"
    blob = ab.encode_acl_bitmap(FIXTURE_BITS)
    assert ab.decode_acl_bitmap(blob) == FIXTURE_BITS
    path.write_bytes(blob)
    return path


@pytest.fixture(scope="module")
def search_binaries(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.fail(
            "ENVIRONMENT BLOCK: no C++ compiler (g++/clang++). "
            "Real search integration CANNOT be skipped while claiming PASS."
        )
    build = tmp_path_factory.mktemp("h1acl_3a6_bin")
    src = EXP_DIR / "main.cpp"
    binaries = {}
    for name, include_dir in HNSW_INCLUDE_DIRS.items():
        if not (include_dir / "hnswlib.h").is_file():
            pytest.fail(f"frozen hnswlib header missing: {include_dir}")
        exe = build / (
            f"search_{name}.exe" if sys.platform == "win32" else f"search_{name}"
        )
        proc = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-O0",
             f"-I{MODULE_3A4}", f"-I{EXP_DIR}", f"-I{include_dir}",
             str(src), "-o", str(exe)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            pytest.fail(
                f"C++ compile failed ({name}):\n{proc.stdout}\n{proc.stderr}"
            )
        binaries[name] = exe
    return binaries


def run_search(exe, fixture):
    return subprocess.run(
        [str(exe), str(fixture)], capture_output=True, text=True
    )


def parse_output(text):
    lines = text.strip().splitlines()
    out = {"lines": lines, "checks": {}}
    assert lines, "empty C++ output"
    assert lines[0] == "LOAD OK", lines[0]
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "UNFILTERED":
            out["unfiltered"] = [int(x) for x in parts[1:]]
        elif parts[0] == "FILTERED":
            out["filtered"] = [int(x) for x in parts[1:]]
        elif parts[0] == "META":
            out["meta"] = dict(p.split("=", 1) for p in parts[1:])
        elif parts[0] == "CHECK":
            key, value = parts[1].split("=", 1)
            out["checks"][key] = value
        elif parts[0] == "RESULT":
            out["result"] = parts[1]
    return out


def label_bit(label):
    offset = label - 100000
    assert offset >= 0 and offset % 17 == 0
    idx = offset // 17
    assert 0 <= idx < N_MEMBERS
    return FIXTURE_BITS[idx]


def assert_valid_result(proc, name):
    assert proc.returncode == 0, f"{name}: {proc.stdout}\n{proc.stderr}"
    out = parse_output(proc.stdout)
    assert out.get("result") == "PASS", f"{name}: {proc.stdout}"
    assert set(out["checks"]) == REQUIRED_CHECKS
    assert all(v == "1" for v in out["checks"].values()), out["checks"]
    assert out["meta"]["n"] == str(N_MEMBERS)
    assert out["meta"]["k"] == str(K)
    assert int(out["meta"]["callback_calls"]) > 0
    assert len(out["unfiltered"]) == K
    assert len(out["filtered"]) >= 1
    assert all(label_bit(label) == 0 for label in out["unfiltered"])
    assert all(label_bit(label) == 1 for label in out["filtered"])
    assert set(out["filtered"]).isdisjoint(out["unfiltered"])
    return out


def test_real_search_integration_both_header_sets(acl_fixture, search_binaries):
    results = {}
    for name, exe in search_binaries.items():
        proc = run_search(exe, acl_fixture)
        results[name] = assert_valid_result(proc, name)
    # Instrumented and pristine must behave identically on result labels.
    assert set(results["pristine"]["unfiltered"]) == set(
        results["rm2"]["unfiltered"]
    )
    assert set(results["pristine"]["filtered"]) == set(
        results["rm2"]["filtered"]
    )


def test_repeatable(acl_fixture, search_binaries):
    # Same binary + same fixture -> byte-identical output on repeated runs.
    for name, exe in search_binaries.items():
        first = run_search(exe, acl_fixture)
        second = run_search(exe, acl_fixture)
        assert first.returncode == 0 and second.returncode == 0
        assert first.stdout == second.stdout, f"{name}: non-repeatable output"


def test_no_secret_material_in_output(acl_fixture, search_binaries):
    for name, exe in search_binaries.items():
        proc = run_search(exe, acl_fixture)
        body = proc.stdout + proc.stderr
        assert "H1ACL01" not in body
        assert str(acl_fixture) not in body
        assert "bitmap" not in body.lower()
