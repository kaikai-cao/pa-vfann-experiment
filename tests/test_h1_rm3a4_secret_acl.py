"""H1-RM.3A.4 / 3A.5 — Secret ACL fixture, pair integrity and filter adapter tests.

Independent data-layer and callback-contract verification: no HNSW query, no
C0/C1/C2, no attack evaluation, no real ACL instance, and no secret material
written to logs. The 3A.5 tests call the filter functor directly; they do NOT
run HNSW search.

Run:
    python -m pytest tests/test_h1_rm3a4_secret_acl.py -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import acl_bitmap as ab  # noqa: E402  (after sys.path injection)

# Fixed test vector — NOT a real experiment ACL.
FIXED_VEC = [int((i % 3) == 0) for i in range(40)]
PUBLIC_SEED = 20261125
N_MEMBERS = 40


# --------------------------------------------------------------------------- #
# helpers: compile C++ driver into tmp dir (compiler absence = environment block)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def cpp_driver(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.fail(
            "ENVIRONMENT BLOCK: no C++ compiler (g++/clang++). "
            "C++ interop acceptance CANNOT be skipped while claiming PASS."
        )
    build = tmp_path_factory.mktemp("h1acl_cpp")
    exe = build / ("acl_test.exe" if sys.platform == "win32" else "acl_test")
    src = MODULE_DIR / "test_acl_bitmap.cpp"
    proc = subprocess.run(
        [compiler, "-std=c++17", "-Wall", "-Wextra", "-O0",
         f"-I{MODULE_DIR}", str(src), "-o", str(exe)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"C++ compile failed:\n{proc.stdout}\n{proc.stderr}")
    return exe


def run_cpp(exe: Path, fixture: Path, *labels: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(exe), str(fixture), *(str(x) for x in labels)],
        capture_output=True, text=True,
    )


# --------------------------------------------------------------------------- #
# 1. target pre-selection: reproducible, unique, legal, ACL-independent
# --------------------------------------------------------------------------- #
def test_target_selection_reproducible_unique_legal_and_acl_independent():
    t1 = ab.select_targets(1000, 8, PUBLIC_SEED)
    t2 = ab.select_targets(1000, 8, PUBLIC_SEED)
    assert t1 == t2
    assert len(t1) == len(set(t1)) == 8
    assert all(isinstance(x, int) and 0 <= x < 1000 for x in t1)
    # Different public seed -> different set (determinism is seed-bound).
    assert ab.select_targets(1000, 8, PUBLIC_SEED + 1) != t1
    # Signature accepts ONLY public quantities; no ACL argument exists.
    import inspect
    params = inspect.signature(ab.select_targets).parameters
    assert set(params) == {"n_members", "target_count", "public_seed"}
    # Edge cases.
    assert ab.select_targets(10, 0, PUBLIC_SEED) == []
    assert ab.select_targets(10, 10, PUBLIC_SEED) == list(range(10))
    with pytest.raises(ValueError):
        ab.select_targets(10, 11, PUBLIC_SEED)


# --------------------------------------------------------------------------- #
# 2. deterministic injected random source
# --------------------------------------------------------------------------- #
def test_injected_deterministic_random_source():
    all_auth = ab.sample_acl_bitmap(N_MEMBERS, _randbelow=lambda bound: 0)
    assert all_auth == [1] * N_MEMBERS
    none_auth = ab.sample_acl_bitmap(N_MEMBERS, _randbelow=lambda bound: bound - 1)
    assert none_auth == [0] * N_MEMBERS
    # exact rational probability: p_num/p_den with injected sequence
    seq = iter([0, 9, 0, 9, 9] * 20)  # draws from p_den=10
    partial = ab.sample_acl_bitmap(
        5, p_num=1, p_den=10, _randbelow=lambda bound: next(seq)
    )
    assert partial == [1, 0, 1, 0, 0]
    with pytest.raises(ValueError):
        ab.sample_acl_bitmap(10, p_num=11, p_den=10)


# --------------------------------------------------------------------------- #
# 3. default generation uses secrets.randbelow, not predictable global RNG
# --------------------------------------------------------------------------- #
def test_default_uses_csprng(monkeypatch):
    calls = {"n": 0}

    def spy(bound):
        calls["n"] += 1
        assert bound == 10
        return 0  # all authorized under p=1/10 for deterministic assertion

    monkeypatch.setattr(ab.secrets, "randbelow", spy)
    result = ab.sample_acl_bitmap(N_MEMBERS)
    assert calls["n"] == N_MEMBERS
    assert result == [1] * N_MEMBERS
    # source must not CALL random.seed / use the global random module.
    # (The docstring mentions "random.seed" only as prose, so match call form.)
    src = (MODULE_DIR / "acl_bitmap.py").read_text(encoding="utf-8")
    assert "random.seed(" not in src
    assert "import random" not in src
    assert "from random" not in src


# --------------------------------------------------------------------------- #
# 4. A0/A1 differ only at target
# --------------------------------------------------------------------------- #
def test_pair_diff_only_target():
    base = FIXED_VEC
    for u in (0, 1, 17, 39):
        a0, a1 = ab.derive_target_pair(base, u)
        assert ab.diff_indices(a0, a1) == [u]
        assert a0[u] == 0 and a1[u] == 1
        assert all(a0[i] == a1[i] == base[i] for i in range(len(base)) if i != u)


# --------------------------------------------------------------------------- #
# 5. multi-target pairing does not pollute
# --------------------------------------------------------------------------- #
def test_multi_target_no_pollution():
    base = FIXED_VEC
    p7 = ab.derive_target_pair(base, 7)
    p9 = ab.derive_target_pair(base, 9)
    assert ab.diff_indices(*p7) == [7]
    assert ab.diff_indices(*p9) == [9]
    # each pair leaves the other target's bit as base
    assert p7[0][9] == p7[1][9] == base[9]
    assert p9[0][7] == p9[1][7] == base[7]
    # base itself unchanged
    assert base == [int((i % 3) == 0) for i in range(40)]


# --------------------------------------------------------------------------- #
# 6. Python encode/decode bit-exact round-trip
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n", [1, 7, 8, 9, 40, 63, 64, 65])
def test_python_encode_decode_roundtrip(n):
    vec = [int((i * 7 + 3) % 5 == 0) for i in range(n)]
    data = ab.encode_acl_bitmap(vec)
    assert len(data) == 8 + 8 + (n + 7) // 8
    assert ab.decode_acl_bitmap(data) == vec


# --------------------------------------------------------------------------- #
# 7 & 8. Python-written fixture is loaded by C++; correct bit per valid label
# --------------------------------------------------------------------------- #
def test_python_fixture_loaded_by_cpp_and_label_bits(tmp_path, cpp_driver):
    fixture = tmp_path / "fixed_test_vector.bin"
    fixture.write_bytes(ab.encode_acl_bitmap(FIXED_VEC))

    valid_pairs = [(100000 + 17 * i, FIXED_VEC[i]) for i in range(len(FIXED_VEC))]
    labels = [p[0] for p in valid_pairs]
    proc = run_cpp(cpp_driver, fixture, *labels)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "LOAD OK"
    got = {}
    for line in lines[1:]:
        parts = line.split()
        # "LABEL <label> OK <bit>"
        got[int(parts[1])] = int(parts[3])
    for label, bit in valid_pairs:
        assert got[label] == bit


# --------------------------------------------------------------------------- #
# 9. invalid labels and malformed blobs are rejected
# --------------------------------------------------------------------------- #
def test_invalid_labels_rejected(tmp_path, cpp_driver):
    fixture = tmp_path / "v.bin"
    fixture.write_bytes(ab.encode_acl_bitmap(FIXED_VEC))
    proc = run_cpp(cpp_driver, fixture,
                   99999,          # below base
                   100001,         # off step grid
                   100000 + 17 * 40,  # out of range
                   12345)
    assert proc.returncode == 0  # load still OK
    body = proc.stdout
    for label in (99999, 100001, 100000 + 17 * 40, 12345):
        assert f"LABEL {label} REJECT" in body


def test_malformed_blobs_rejected(tmp_path, cpp_driver):
    good = ab.encode_acl_bitmap(FIXED_VEC)

    cases = {
        "bad_magic": b"H2ACL01\x00" + good[8:],
        "truncated": good[:-1],
        "trailing": good + b"\x00",
    }
    # non-zero tail padding: 10 members -> payload 2 bytes, last byte uses
    # only 2 low bits (indices 8,9); bits 2..7 are padding and must stay 0.
    ten = bytearray(ab.encode_acl_bitmap([0] * 10))
    ten[-1] |= 0x04  # set a HIGH padding bit, not a valid low bit
    cases["bad_padding"] = bytes(ten)

    expect = {
        "bad_magic": "BAD_MAGIC",
        "truncated": "TRUNCATED_PAYLOAD",
        "trailing": "TRAILING_BYTES",
        "bad_padding": "BAD_TAIL_PADDING",
    }
    for name, blob in cases.items():
        p = tmp_path / f"{name}.bin"
        p.write_bytes(blob)
        proc = run_cpp(cpp_driver, p)
        assert proc.returncode == 1, f"{name}: {proc.stdout}"
        assert f"LOAD {expect[name]}" in proc.stdout, f"{name}: {proc.stdout}"
    # Python decoder agrees on the same malformed blobs
    with pytest.raises(ValueError):
        ab.decode_acl_bitmap(cases["bad_magic"])
    with pytest.raises(ValueError):
        ab.decode_acl_bitmap(cases["truncated"])
    with pytest.raises(ValueError):
        ab.decode_acl_bitmap(cases["trailing"])
    with pytest.raises(ValueError):
        ab.decode_acl_bitmap(cases["bad_padding"])


# --------------------------------------------------------------------------- #
# 10. no secret bits / seed / real count written to logs
# --------------------------------------------------------------------------- #
def test_no_secret_material_in_logs(capsys, tmp_path, cpp_driver):
    # Library header prints nothing; check it contains no output calls except
    # the status_name table (pure strings) — no cout/printf in the header.
    header = (MODULE_DIR / "acl_bitmap.h").read_text(encoding="utf-8")
    assert "std::cout" not in header
    assert "printf" not in header
    assert "std::cerr" not in header

    # Generation / pairing / encoding must be silent in Python.
    _ = ab.sample_acl_bitmap(N_MEMBERS)
    _ = ab.derive_target_pair(FIXED_VEC, 3)
    _ = ab.encode_acl_bitmap(FIXED_VEC)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""

    # Binary fixture must not embed seed / count / target state / pair marker.
    blob = ab.encode_acl_bitmap(FIXED_VEC)
    assert blob[:8] == b"H1ACL01\x00"
    # Count field is member count (40), NOT the authorized count.
    assert int.from_bytes(blob[8:16], "little") == len(FIXED_VEC) == 40
    assert sum(FIXED_VEC) != 40  # ensure the two are distinguishable in this vector


# --------------------------------------------------------------------------- #
# 11. Phase A — empty bitmap contract is N > 0 in BOTH languages
# --------------------------------------------------------------------------- #
def test_empty_bitmap_encode_rejected():
    # C++ AclBitmap::load() rejects count == 0; Python encode must agree.
    with pytest.raises(ValueError):
        ab.encode_acl_bitmap([])
    # Zero TARGETS is still legal; it is a different quantity from zero MEMBERS.
    assert ab.select_targets(10, 0, PUBLIC_SEED) == []


def test_header_only_zero_count_rejected_by_both_languages(tmp_path, cpp_driver):
    header_only = ab.MAGIC + (0).to_bytes(ab.COUNT_LEN, "little", signed=False)
    with pytest.raises(ValueError):
        ab.decode_acl_bitmap(header_only)
    p = tmp_path / "zero_count.bin"
    p.write_bytes(header_only)
    proc = run_cpp(cpp_driver, p)
    assert proc.returncode == 1
    assert "LOAD BAD_MEMBER_COUNT" in proc.stdout


# --------------------------------------------------------------------------- #
# 12. Phase C — filter adapter compiles against BOTH frozen hnswlib header sets
# --------------------------------------------------------------------------- #
HNSW_INCLUDE_DIRS = {
    "pristine": REPO_ROOT / "third_party" / "hnswlib-v0.9.0" / "hnswlib",
    "rm2": REPO_ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib",
}


@pytest.fixture(scope="module")
def filter_drivers(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.fail(
            "ENVIRONMENT BLOCK: no C++ compiler (g++/clang++). "
            "Adapter compile acceptance CANNOT be skipped while claiming PASS."
        )
    build = tmp_path_factory.mktemp("h1acl_filter")
    src = MODULE_DIR / "test_hnsw_acl_filter.cpp"
    drivers = {}
    for name, include_dir in HNSW_INCLUDE_DIRS.items():
        if not (include_dir / "hnswlib.h").is_file():
            pytest.fail(f"frozen hnswlib header missing: {include_dir}")
        exe = build / (
            f"filter_{name}.exe" if sys.platform == "win32" else f"filter_{name}"
        )
        proc = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-O0",
             f"-I{MODULE_DIR}", f"-I{include_dir}", str(src), "-o", str(exe)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            pytest.fail(
                f"C++ adapter compile failed ({name}):\n{proc.stdout}\n{proc.stderr}"
            )
        drivers[name] = exe
    return drivers


def run_filter(exe, *args):
    return subprocess.run(
        [str(exe), *(str(x) for x in args)], capture_output=True, text=True
    )


def parse_filter_output(text):
    lines = text.strip().splitlines()
    assert lines and lines[0].startswith("LOAD ")
    decisions = {}
    for line in lines[1:]:
        parts = line.split()
        assert len(parts) == 3 and parts[0] == "FILTER"
        assert parts[2] in ("ALLOW", "DENY")
        decisions[parts[1]] = parts[2]
    return lines[0], decisions


def test_filter_adapter_matches_python_vector(tmp_path, filter_drivers):
    # Fixed, non-real vector written by Python; C++ must reproduce it exactly.
    fixture = tmp_path / "adapter_vector.bin"
    fixture.write_bytes(ab.encode_acl_bitmap(FIXED_VEC))
    valid = [100000 + 17 * i for i in range(len(FIXED_VEC))]
    invalid = [99999, 100001, 100000 + 17 * len(FIXED_VEC), 18446744073709551615]
    expected = {
        str(label): ("ALLOW" if FIXED_VEC[i] else "DENY")
        for i, label in enumerate(valid)
    }
    expected.update({str(label): "DENY" for label in invalid})

    for name, exe in filter_drivers.items():
        proc = run_filter(exe, fixture, *(valid + invalid))
        assert proc.returncode == 0, f"{name}: {proc.stdout}\n{proc.stderr}"
        load, got = parse_filter_output(proc.stdout)
        assert load == "LOAD OK", f"{name}: {load}"
        assert got == expected, f"{name}: C++ decisions disagree with Python vector"


def test_filter_denies_unloaded_acl(filter_drivers):
    # An unloaded ACL has n_ == 0; absence of data must never mean "allow".
    for name, exe in filter_drivers.items():
        proc = run_filter(exe, "--unloaded", 100000, 100001, 99999)
        assert proc.returncode == 0, f"{name}: {proc.stdout}"
        load, got = parse_filter_output(proc.stdout)
        assert load == "LOAD UNLOADED"
        assert got == {"100000": "DENY", "100001": "DENY", "99999": "DENY"}


def test_filter_driver_rejects_empty_blob(tmp_path, filter_drivers):
    header_only = ab.MAGIC + (0).to_bytes(ab.COUNT_LEN, "little", signed=False)
    p = tmp_path / "zero_count.bin"
    p.write_bytes(header_only)
    for name, exe in filter_drivers.items():
        proc = run_filter(exe, p, 100000)
        assert proc.returncode == 1, f"{name}: {proc.stdout}"
        assert proc.stdout.strip() == "LOAD BAD_MEMBER_COUNT"


def test_filter_header_is_readonly_and_silent():
    src = (MODULE_DIR / "hnsw_acl_filter.h").read_text(encoding="utf-8")
    assert "class SecretAclFilter : public hnswlib::BaseFilterFunctor" in src
    assert "bool operator()(hnswlib::labeltype id) override" in src
    assert "explicit SecretAclFilter(const h1acl::AclBitmap& acl)" in src
    assert "const h1acl::AclBitmap& acl_" in src
    assert "acl_.lookup_label(" in src
    for banned in ("std::cout", "std::cerr", "printf", "fopen", "ofstream"):
        assert banned not in src, f"adapter must not emit/store secret state: {banned}"
