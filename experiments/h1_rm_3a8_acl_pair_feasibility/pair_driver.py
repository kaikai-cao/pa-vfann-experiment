"""H1-RM.3A.8 — A0/A1 paired-ACL feasibility driver.

FEASIBILITY ONLY. No classifier, no BA/AUC, no attack advantage, no page-level
or physical trace simulation, and no change to any search code.

What this module does
---------------------
1. Pre-select ONE target member u from the FULL public set using a
   PRE-REGISTERED PUBLIC SEED, before any ACL is generated. Selection receives
   only public quantities -- never an ACL, bit, distance, K-hit position,
   observer trace or any search result.
2. Generate ONE private base ACL from the system CSPRNG.
3. Derive a counterfactual pair (A0, A1) that is bit-identical except at u:
       A0[u] = 0 (unauthorized), A1[u] = 1 (authorized), A0[i] = A1[i] for i!=u.
4. Verify the single-bit-pair invariants, encode both ACLs with the existing
   3A.4 encoder, and write the blobs to a CALLER-SUPPLIED PRIVATE directory.
5. Drive the UNMODIFIED 3A.7 C0/C1/C2 harness once per ACL, into separate
   output directories, and analyse three INDEPENDENT layers:
       - pairing integrity  (is the pair really one bit apart)
       - observation feasibility (did u enter internal/observer views)
       - trace sensitivity (does a one-bit change coincide with a trace change)

The last layer is sensitivity evidence, NOT a statistical leakage proof.
A0/A1 are researcher-side counterfactuals: a real attacker never sees both.

All generated ACL blobs, diagnostics and traces live ONLY in directories the
caller passes in (tests use pytest tmp_path). This module writes NOTHING into
the repository and never prints bitmap contents or private file paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_3A4 = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
HARNESS_DIR = REPO_ROOT / "experiments" / "h1_rm_3a7_secret_acl_c0c1c2_smoke"
RM2_INCLUDE = (
    REPO_ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib"
)
if str(MODULE_3A4) not in sys.path:
    sys.path.insert(0, str(MODULE_3A4))

import acl_bitmap as ab  # noqa: E402

# ---- pre-registered public constants (frozen for this feasibility stage) ----
PUBLIC_SEED = "H1-RM.3A8-TARGET-SEED-20261126"
N_MEMBERS = 200
TARGET_COUNT = 1
LABEL_BASE = 100000
LABEL_STEP = 17
GROUPS = ("C0", "C1", "C2")
K = 5
EF = 64
N_QUERIES = 6

FORBIDDEN_OBS_KEYS = {
    "extra", "internal_id", "auth_hits", "khit_event_index", "n_filter_ok",
    "n_filter_check", "result_all_authorized",
}
FORBIDDEN_OBS_EVENTS = {"filter_check", "result_add", "result_remove"}


@dataclass
class PairManifest:
    """Researcher-side in-memory description of one counterfactual pair."""

    n: int
    target: int
    target_label: int
    a0: list[int]
    a1: list[int]
    diff: list[int]
    a0_path: Path | None = None
    a1_path: Path | None = None

    def summary(self) -> dict[str, Any]:
        # No bitmap contents, no private paths, no authorized count.
        return {
            "n": self.n,
            "target": self.target,
            "target_label": self.target_label,
            "target_seed": PUBLIC_SEED,
            "diff": self.diff,
            "a0_target_bit": self.a0[self.target],
            "a1_target_bit": self.a1[self.target],
        }


def select_target(n: int = N_MEMBERS, public_seed: str = PUBLIC_SEED) -> int:
    """Pre-register the target from public data ONLY, before any ACL exists."""
    chosen = ab.select_targets(n, TARGET_COUNT, public_seed)
    assert len(chosen) == TARGET_COUNT
    return chosen[0]


def build_pair(
    private_dir: Path,
    *,
    n: int = N_MEMBERS,
    public_seed: str = PUBLIC_SEED,
) -> PairManifest:
    """Select target, sample one CSPRNG ACL, derive (A0, A1), write blobs.

    Order matters: select_target() is called BEFORE sample_acl_bitmap(), and
    neither the seed nor the target depends on the generated bits.
    """
    private_dir.mkdir(parents=True, exist_ok=True)
    u = select_target(n, public_seed)
    base = ab.sample_acl_bitmap(n)  # system CSPRNG; not seed-controlled
    a0, a1 = ab.derive_target_pair(base, u)
    diff = ab.diff_indices(a0, a1)

    if diff != [u]:
        raise RuntimeError("pair invariant violated: diff != {u}")
    if a0[u] != 0 or a1[u] != 1:
        raise RuntimeError("pair invariant violated: target bits not 0/1")

    p0 = private_dir / "acl_A0.bin"
    p1 = private_dir / "acl_A1.bin"
    p0.write_bytes(ab.encode_acl_bitmap(a0))
    p1.write_bytes(ab.encode_acl_bitmap(a1))
    # Round-trip through the SAME encoder used by the C++ loader contract.
    if ab.decode_acl_bitmap(p0.read_bytes()) != a0:
        raise RuntimeError("A0 encode/decode mismatch")
    if ab.decode_acl_bitmap(p1.read_bytes()) != a1:
        raise RuntimeError("A1 encode/decode mismatch")

    return PairManifest(
        n=n,
        target=u,
        target_label=LABEL_BASE + LABEL_STEP * u,
        a0=a0,
        a1=a1,
        diff=diff,
        a0_path=p0,
        a1_path=p1,
    )


def compile_harness(exe_path: Path) -> Path:
    """Compile the UNMODIFIED 3A.7 harness. No source file is touched."""
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        raise RuntimeError("ENVIRONMENT BLOCK: no C++ compiler")
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
         "-DHNSWLIB_RM2_TRACE_ENABLED=1",
         f"-I{MODULE_3A4}", f"-I{HARNESS_DIR}", f"-I{RM2_INCLUDE}",
         str(HARNESS_DIR / "main.cpp"), "-o", str(exe_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"harness compile failed:\n{proc.stderr}")
    return exe_path


def run_harness(exe: Path, fixture: Path, outdir: Path) -> subprocess.CompletedProcess:
    """Run one ACL through the harness into its own output directory."""
    outdir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(exe), str(fixture), str(outdir)], capture_output=True, text=True
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _events(outdir: Path, kind: str, group: str) -> list[dict[str, Any]]:
    return [
        r for r in _read_jsonl(outdir / f"{kind}_{group}.jsonl")
        if "event_type" in r
    ]


def _summaries(outdir: Path, group: str) -> list[dict[str, Any]]:
    return [
        r for r in _read_jsonl(outdir / f"internal_diagnostics_{group}.jsonl")
        if r.get("record_type") == "group_summary"
    ]


def cpp_loader_bits(fixture: Path, labels: list[int], exe_path: Path) -> dict[int, int | None]:
    """Query the C++ AclBitmap loader via the frozen 3A.4 driver."""
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        raise RuntimeError("ENVIRONMENT BLOCK: no C++ compiler")
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [compiler, "-std=c++17", "-O2", f"-I{MODULE_3A4}",
         str(MODULE_3A4 / "test_acl_bitmap.cpp"), "-o", str(exe_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"loader driver compile failed:\n{proc.stderr}")
    run = subprocess.run(
        [str(exe_path), str(fixture)] + [str(x) for x in labels],
        capture_output=True, text=True,
    )
    if run.returncode != 0 or not run.stdout.startswith("LOAD OK"):
        raise RuntimeError(f"C++ loader rejected fixture: {run.stdout}")
    out: dict[int, int | None] = {}
    for line in run.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "LABEL" and parts[2] == "OK":
            out[int(parts[1])] = int(parts[3])
        elif len(parts) == 3 and parts[0] == "LABEL" and parts[2] == "REJECT":
            out[int(parts[1])] = None
    return out


@dataclass
class TargetVisibility:
    """Three INDEPENDENT conditions for one (group, ACL) target observation."""

    group: str
    acl: str
    internal_distance_eval: bool
    internal_filter_check: bool
    observer_visible: bool


@dataclass
class TraceComparison:
    group: str
    a0_event_count: int
    a1_event_count: int
    a0_schema: dict[str, list[str]] = field(default_factory=dict)
    a1_schema: dict[str, list[str]] = field(default_factory=dict)
    schemas_equal: bool = True
    content_equal: bool = True
    first_difference: dict[str, Any] | None = None


def _schema(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}
    for e in events:
        out.setdefault(e["event_type"], set()).update(e.keys())
    return {k: sorted(v) for k, v in sorted(out.items())}


def analyse_group(
    group: str,
    out_a0: Path,
    out_a1: Path,
    target_label: int,
) -> tuple[TargetVisibility, TargetVisibility, TraceComparison]:
    """Analyse one C-group for both ACLs. No statistical claim is made."""
    vis: list[TargetVisibility] = []
    for acl, outdir in (("A0", out_a0), ("A1", out_a1)):
        int_ev = _events(outdir, "internal_diagnostics", group)
        obs_ev = _events(outdir, "observer_proxy", group)
        vis.append(TargetVisibility(
            group=group,
            acl=acl,
            internal_distance_eval=any(
                e["event_type"] == "distance_eval"
                and e.get("external_id") == target_label for e in int_ev),
            internal_filter_check=any(
                e["event_type"] == "filter_check"
                and e.get("external_id") == target_label for e in int_ev),
            observer_visible=any(
                e.get("external_id") == target_label for e in obs_ev),
        ))

    obs0 = _events(out_a0, "observer_proxy", group)
    obs1 = _events(out_a1, "observer_proxy", group)
    s0, s1 = _schema(obs0), _schema(obs1)
    cmp = TraceComparison(
        group=group,
        a0_event_count=len(obs0),
        a1_event_count=len(obs1),
        a0_schema=s0,
        a1_schema=s1,
        schemas_equal=(s0 == s1),
    )
    # Sensitivity only: do the two proxy traces differ in observable content?
    # event_index is intentionally dense/observer-local and is included as-is.
    if obs0 != obs1:
        cmp.content_equal = False
        for i, (x, y) in enumerate(zip(obs0, obs1)):
            if x != y:
                cmp.first_difference = {"position": i, "A0": x, "A1": y}
                break
        if cmp.first_difference is None:
            cmp.first_difference = {"reason": "event_count", "A0": len(obs0),
                                    "A1": len(obs1)}
    return vis[0], vis[1], cmp


def analyse_run(
    manifest: PairManifest,
    out_a0: Path,
    out_a1: Path,
    stdout_a0: str,
    stdout_a1: str,
) -> dict[str, Any]:
    """Assemble the three-layer feasibility report (no attack metric)."""
    vis: list[TargetVisibility] = []
    comps: list[TraceComparison] = []
    for g in GROUPS:
        v0, v1, cmp = analyse_group(g, out_a0, out_a1, manifest.target_label)
        vis.extend([v0, v1])
        comps.append(cmp)

    def as_dict(v: TargetVisibility) -> dict[str, Any]:
        return {
            "group": v.group, "acl": v.acl,
            "internal_distance_eval": v.internal_distance_eval,
            "internal_filter_check": v.internal_filter_check,
            "observer_visible": v.observer_visible,
        }

    def comp_dict(c: TraceComparison) -> dict[str, Any]:
        return {
            "group": c.group,
            "a0_event_count": c.a0_event_count,
            "a1_event_count": c.a1_event_count,
            "schemas_equal": c.schemas_equal,
            "content_equal": c.content_equal,
            "first_difference": c.first_difference,
        }

    khit_a0 = [
        s for g in GROUPS for s in _summaries(out_a0, g)
        if s["khit_event_index"] >= 0
    ]
    khit_a1 = [
        s for g in GROUPS for s in _summaries(out_a1, g)
        if s["khit_event_index"] >= 0
    ]
    return {
        "pair": manifest.summary(),
        "pair_integrity": {
            "member_counts_equal": len(manifest.a0) == len(manifest.a1),
            "diff_exactly_target": manifest.diff == [manifest.target],
            "a0_target_unauthorized": manifest.a0[manifest.target] == 0,
            "a1_target_authorized": manifest.a1[manifest.target] == 1,
        },
        "search_runnable": {
            "a0_all_results_authorized": "all_results_authorized=1" in stdout_a0,
            "a1_all_results_authorized": "all_results_authorized=1" in stdout_a1,
            "a0_c2_khit_seen": "c2_khit_seen=1" in stdout_a0,
            "a1_c2_khit_seen": "c2_khit_seen=1" in stdout_a1,
            "a0_khit_summary_count": len(khit_a0),
            "a1_khit_summary_count": len(khit_a1),
        },
        "target_visibility": [as_dict(v) for v in vis],
        "trace_comparison": [comp_dict(c) for c in comps],
        "disclaimer": (
            "Layer-3 trace sensitivity is NOT a statistical leakage proof. "
            "A0/A1 are researcher counterfactuals; no attacker observes both."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: build a private pair, run both ACLs, print the feasibility report.

    Usage: pair_driver.py <private_workdir>
    All artifacts stay under <private_workdir>; nothing is written to the repo.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: pair_driver.py <private_workdir>", file=sys.stderr)
        return 2
    work = Path(args[0]).resolve()
    private = work / "private"
    manifest = build_pair(private)
    exe = compile_harness(work / "harness")
    out0, out1 = work / "trace_A0", work / "trace_A1"
    r0 = run_harness(exe, manifest.a0_path, out0)
    r1 = run_harness(exe, manifest.a1_path, out1)
    report = analyse_run(manifest, out0, out1, r0.stdout, r1.stdout)
    (work / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report["pair"], ensure_ascii=False))
    print(json.dumps(report["pair_integrity"], ensure_ascii=False))
    print(json.dumps(report["search_runnable"], ensure_ascii=False))
    return 0 if (r0.returncode == 0 and r1.returncode == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
