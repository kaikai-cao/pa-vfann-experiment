"""H1-RM.3A.10 — DEV-1 independent-pair data generation and observer-only features.

This module implements ONLY the DEV-1 data pipeline:
  1. generate independent private base ACLs and derive A0/A1 with one fixed flip;
  2. verify the frozen H1ACL01 format through the existing C++ loader driver;
  3. run the UNMODIFIED 3A.7 C0/C1/C2 harness for both ACL states;
  4. extract frozen observer-only features from observer_proxy traces;
  5. write a private manifest and private feature datasets.

It deliberately does NOT train a classifier, select C, normalize features,
compute BA/AUC/TPR/FPR, estimate variance, or start PILOT/CONFIRM.

All private artifacts are written only to a CALLER-SUPPLIED private directory
outside the repository. The CLI refuses a private root inside the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_3A4 = REPO_ROOT / "experiments" / "h1_rm_3a4_secret_acl"
HARNESS_DIR = REPO_ROOT / "experiments" / "h1_rm_3a7_secret_acl_c0c1c2_smoke"
PAIR_DIR = REPO_ROOT / "experiments" / "h1_rm_3a8_acl_pair_feasibility"
PROTOCOL_PATH = REPO_ROOT / "experiments" / "h1_rm_3a9_statistical_protocol" / "PROTOCOL.md"
RM2_INCLUDE = REPO_ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib"

for _p in (MODULE_3A4, PAIR_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import acl_bitmap as ab  # noqa: E402
import pair_driver as pd  # noqa: E402

# --------------------------------------------------------------------------- #
# Frozen constants (DEV-1 task package + R5/R5.1 protocol)
# --------------------------------------------------------------------------- #
N_MEMBERS = 200
TARGET_INDEX = 103
TARGET_LABEL = 101751
LABEL_BASE = 100000
LABEL_STEP = 17
PUBLIC_SEED = pd.PUBLIC_SEED
SPLIT_SEED = "H1-RM.3A9-SPLIT-SEED-20261126"
NAMESPACE = "DEV"
N_QUERIES = 6
QUERY_IDS = tuple(range(N_QUERIES))
GROUPS = ("C0", "C1", "C2")
OBSERVER_KINDS = ("C0", "C1", "C2")
ACL_STATES = ("A0", "A1")

ALLOWED_EVENT_TYPES = (
    "distance_eval",
    "candidate_consider",
    "candidate_pop",
    "stop_check",
    "search_stop",
)
ALLOWED_EVENT_TYPE_SET = frozenset(ALLOWED_EVENT_TYPES)
INTERNAL_ONLY_EVENTS = frozenset({"filter_check", "result_add", "result_remove"})
BASE_OBS_KEYS = frozenset({"query_id", "event_index", "group", "event_type"})
DIST_OBS_KEYS = BASE_OBS_KEYS | {"external_id", "level", "dist_bits"}
FORBIDDEN_OBS_KEYS = frozenset(
    {
        "extra",
        "internal_id",
        "auth_hits",
        "khit_event_index",
        "n_filter_ok",
        "n_filter_check",
        "result_all_authorized",
        "pair_id",
        "pair_label",
        "target_truth",
        "acl",
        "record_type",
    }
)
AGGREGATIONS = ("mean", "min", "max", "std")

PER_QUERY_METRICS = (
    "observer_event_count",
    "event_count_distance_eval",
    "event_count_candidate_consider",
    "event_count_candidate_pop",
    "event_count_stop_check",
    "event_count_search_stop",
    "target_visible",
    "target_count",
    "target_first_index",
    "target_last_index",
    "target_dist_value",
    "target_level",
    "stop_check_present",
    "stop_check_count",
    "stop_check_first_index",
    "search_stop_present",
    "search_stop_count",
    "search_stop_first_index",
    "last_type_distance_eval",
    "last_type_candidate_consider",
    "last_type_candidate_pop",
    "last_type_stop_check",
    "last_type_search_stop",
    "distance_eval_level_min",
    "distance_eval_level_max",
    "distance_eval_level_mean",
    "distance_eval_dist_min",
    "distance_eval_dist_max",
    "distance_eval_dist_mean",
)
VISIBLE_QUERY_COUNT_COLUMN = "f__target_visible_query_count"
LABEL_COLUMN = "label"
FEATURE_COLUMNS = tuple(
    [f"f__{metric}__{agg}" for metric in PER_QUERY_METRICS for agg in AGGREGATIONS]
    + [VISIBLE_QUERY_COUNT_COLUMN]
)
FEATURE_DIM = len(FEATURE_COLUMNS)
FEATURE_SCHEMA_SHA = hashlib.sha256(
    ("\n".join(FEATURE_COLUMNS) + "\n").encode("utf-8")
).hexdigest()

DIST_BITS_RE = re.compile(r"^0x[0-9a-f]{8}$")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class Dev1Stop(Exception):
    """Global stop condition; never downgrade to CONDITIONAL/READY."""


class StructuralPairFailure(Dev1Stop):
    """A single pair failed a structural check and is recorded, not retried."""


class TechnicalPairFailure(Dev1Stop):
    """A single pair failed for a technical reason and is recorded."""


class SchemaChangeError(Dev1Stop):
    """Observer schema changed; must stop and audit the observation boundary."""


class LeakageError(Dev1Stop):
    """Forbidden private/internal information reached the feature boundary."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha(obj: Any) -> str:
    return _sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assert_private_root(private_root: Path) -> Path:
    """Refuse any private artifact location inside the repository."""
    root = Path(private_root).resolve()
    repo = REPO_ROOT.resolve()
    try:
        inside = root == repo or repo in root.parents
    except TypeError:  # pragma: no cover - defensive across Python versions
        inside = str(root).lower().startswith(str(repo).lower())
    if inside:
        raise Dev1Stop("private_root must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


def decode_dist_bits(value: Any) -> float:
    """Decode 3A.7 dist_bits exactly as written by float_bits()/hex32()."""
    if not isinstance(value, str) or not DIST_BITS_RE.match(value):
        raise SchemaChangeError("dist_bits is not an 0x%08x string")
    raw = int(value, 16)
    # 3A.7 uses std::memcpy(float -> uint32) and prints that integer in hex.
    # On the frozen little-endian toolchain this is exactly "<f" bit order.
    return float(struct.unpack("<f", raw.to_bytes(4, "little", signed=False))[0])


def validate_frozen_constants() -> dict[str, Any]:
    target = pd.select_target(N_MEMBERS, PUBLIC_SEED)
    if target != TARGET_INDEX:
        raise Dev1Stop("frozen public target selection no longer yields u=103")
    label = LABEL_BASE + LABEL_STEP * TARGET_INDEX
    if label != TARGET_LABEL:
        raise Dev1Stop("frozen target label mismatch")
    if tuple(pd.GROUPS) != GROUPS:
        raise Dev1Stop("3A.7 groups differ from frozen C0/C1/C2")
    if pd.N_QUERIES != N_QUERIES or pd.K != 5 or pd.EF != 64:
        raise Dev1Stop("3A.7 search constants differ from frozen harness")
    if pd.N_MEMBERS != N_MEMBERS:
        raise Dev1Stop("3A.8 member count differs from frozen value")
    return {
        "target": target,
        "target_label": label,
        "target_seed": PUBLIC_SEED,
        "namespace": NAMESPACE,
        "split_seed": SPLIT_SEED,
        "n_members": N_MEMBERS,
        "n_queries": N_QUERIES,
        "groups": list(GROUPS),
        "aggregations": list(AGGREGATIONS),
        "feature_dim": FEATURE_DIM,
        "feature_columns_sha256": FEATURE_SCHEMA_SHA,
    }


# --------------------------------------------------------------------------- #
# Pair generation (same primitive order as 3A.8, with private base digest)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DevPair:
    pair_id: str
    n: int
    target: int
    target_label: int
    base_digest: str
    a0: tuple[int, ...]
    a1: tuple[int, ...]
    diff: tuple[int, ...]
    a0_path: Path
    a1_path: Path

    def invariant(self) -> dict[str, Any]:
        return {
            "member_counts_equal": len(self.a0) == len(self.a1) == self.n,
            "diff_exactly_target": list(self.diff) == [self.target],
            "a0_target_unauthorized": self.a0[self.target] == 0,
            "a1_target_authorized": self.a1[self.target] == 1,
            "non_target_bits_equal": all(
                self.a0[i] == self.a1[i]
                for i in range(self.n)
                if i != self.target
            ),
        }

    def safe_summary(self) -> dict[str, Any]:
        # No bitmap bits, no authorized count, no private paths.
        return {
            "pair_id": self.pair_id,
            "n": self.n,
            "target": self.target,
            "target_label": self.target_label,
            "target_seed": PUBLIC_SEED,
            "diff": list(self.diff),
            "base_acl_sha256": self.base_digest,
            "a0_blob_sha256": _sha256_file(self.a0_path),
            "a1_blob_sha256": _sha256_file(self.a1_path),
        }


def build_dev_pair(pair_dir: Path, pair_id: str) -> DevPair:
    """Build one independent pair using the frozen 3A.4 primitives and 3A.8 order."""
    private = pair_dir / "private"
    private.mkdir(parents=True, exist_ok=False)

    # Same order as 3A.8: public target selection BEFORE private ACL sampling.
    u = pd.select_target(N_MEMBERS, PUBLIC_SEED)
    if u != TARGET_INDEX:
        raise StructuralPairFailure("target selection drift")
    base = ab.sample_acl_bitmap(N_MEMBERS)  # system CSPRNG; never seeded
    base_digest = _sha256_bytes(bytes(base))
    a0_list, a1_list = ab.derive_target_pair(base, u)
    diff = ab.diff_indices(a0_list, a1_list)
    if diff != [u] or a0_list[u] != 0 or a1_list[u] != 1:
        raise StructuralPairFailure("pair invariant violated at generation")

    p0 = private / "acl_A0.bin"
    p1 = private / "acl_A1.bin"
    p0.write_bytes(ab.encode_acl_bitmap(a0_list))
    p1.write_bytes(ab.encode_acl_bitmap(a1_list))
    if ab.decode_acl_bitmap(p0.read_bytes()) != a0_list:
        raise StructuralPairFailure("A0 encode/decode mismatch")
    if ab.decode_acl_bitmap(p1.read_bytes()) != a1_list:
        raise StructuralPairFailure("A1 encode/decode mismatch")

    pair = DevPair(
        pair_id=pair_id,
        n=N_MEMBERS,
        target=u,
        target_label=TARGET_LABEL,
        base_digest=base_digest,
        a0=tuple(a0_list),
        a1=tuple(a1_list),
        diff=tuple(diff),
        a0_path=p0,
        a1_path=p1,
    )
    inv = pair.invariant()
    if not all(inv.values()):
        raise StructuralPairFailure("pair invariant violated after encoding")
    return pair


# --------------------------------------------------------------------------- #
# Frozen C++ tools: compile once, invoke per pair
# --------------------------------------------------------------------------- #
def compile_tools(work_root: Path) -> tuple[Path, Path, str]:
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        raise Dev1Stop("ENVIRONMENT BLOCK: no C++ compiler")
    bin_dir = work_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    harness = pd.compile_harness(bin_dir / "h1rm3a7_smoke")

    loader = bin_dir / "test_acl_bitmap"
    proc = subprocess.run(
        [compiler, "-std=c++17", "-O2", f"-I{MODULE_3A4}",
         str(MODULE_3A4 / "test_acl_bitmap.cpp"), "-o", str(loader)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise Dev1Stop(f"loader driver compile failed:\n{proc.stderr}")

    version = subprocess.run(
        [compiler, "--version"], capture_output=True, text=True
    ).stdout.splitlines()
    return harness, loader, version[0] if version else compiler


def query_loader(loader: Path, fixture: Path, labels: Sequence[int]) -> dict[int, int | None]:
    proc = subprocess.run(
        [str(loader), str(fixture)] + [str(x) for x in labels],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.startswith("LOAD OK"):
        raise StructuralPairFailure("C++ loader rejected fixture")
    out: dict[int, int | None] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "LABEL" and parts[2] == "OK":
            out[int(parts[1])] = int(parts[3])
        elif len(parts) == 3 and parts[0] == "LABEL" and parts[2] == "REJECT":
            out[int(parts[1])] = None
        elif parts and parts[0] == "LOAD":
            continue
        else:
            raise StructuralPairFailure("unexpected loader output")
    return out


def verify_loader(pair: DevPair, loader: Path) -> dict[str, Any]:
    labels = [
        TARGET_LABEL - LABEL_STEP,
        TARGET_LABEL,
        TARGET_LABEL + LABEL_STEP,
    ]
    result: dict[str, Any] = {}
    for state, path, bits in (
        ("A0", pair.a0_path, pair.a0),
        ("A1", pair.a1_path, pair.a1),
    ):
        got = query_loader(loader, path, labels)
        if any(got.get(label) is None for label in labels):
            raise StructuralPairFailure(f"{state} loader rejected a valid label")
        expected = {label: bits[(label - LABEL_BASE) // LABEL_STEP] for label in labels}
        if got != expected:
            raise StructuralPairFailure(f"{state} loader bit mismatch")
        result[state] = {
            "load": "OK",
            "target_bit": got[TARGET_LABEL],
            "queried_labels": list(labels),
            "all_queried_bits_match": True,
        }
    return result


# --------------------------------------------------------------------------- #
# Observer parsing / schema audit (feature boundary)
# --------------------------------------------------------------------------- #
def _validate_observer_notice(notice: dict[str, Any]) -> dict[str, Any]:
    expected_filtered = set(INTERNAL_ONLY_EVENTS)
    if notice.get("trust") != "untrusted_observer_view":
        raise SchemaChangeError("observer notice trust changed")
    if notice.get("trace_kind") != "logical_observation_proxy":
        raise SchemaChangeError("observer trace_kind changed")
    if notice.get("is_physical_page_trace") is not False:
        raise SchemaChangeError("observer trace was marked physical")
    if set(notice.get("filtered_internal_event_types", [])) != expected_filtered:
        raise SchemaChangeError("observer filtered event set changed")
    return {
        "trust": notice["trust"],
        "trace_kind": notice["trace_kind"],
        "is_physical_page_trace": False,
        "filtered_internal_event_types": sorted(expected_filtered),
    }


def parse_observer_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Parse one observer_proxy JSONL and enforce the frozen whitelist."""
    rows = read_jsonl(path)
    notices = [r for r in rows if r.get("record_type", "").endswith("notice")]
    if len(notices) != 1:
        raise SchemaChangeError("observer notice must appear exactly once")
    notice = _validate_observer_notice(notices[0])

    events = [r for r in rows if "event_type" in r]
    if len(events) + len(notices) != len(rows):
        raise SchemaChangeError("unexpected observer record type")

    schema: dict[str, list[str]] = {}
    for event in events:
        event_type = event.get("event_type")
        if event_type not in ALLOWED_EVENT_TYPE_SET:
            raise SchemaChangeError(f"schema change: event_type={event_type!r}")
        if event_type in INTERNAL_ONLY_EVENTS:
            raise LeakageError("internal-only event reached observer")
        keys = set(event)
        expected = DIST_OBS_KEYS if event_type == "distance_eval" else BASE_OBS_KEYS
        if keys != expected:
            if keys & FORBIDDEN_OBS_KEYS:
                raise LeakageError("forbidden field reached observer")
            raise SchemaChangeError(f"schema change for {event_type}: {sorted(keys)}")
        if not isinstance(event.get("query_id"), int) or event["query_id"] not in QUERY_IDS:
            raise SchemaChangeError("query_id outside frozen 0..5")
        if not isinstance(event.get("event_index"), int) or event["event_index"] < 0:
            raise SchemaChangeError("event_index invalid")
        if event.get("group") not in GROUPS:
            raise SchemaChangeError("group outside frozen C0/C1/C2")
        if event_type == "distance_eval":
            if not isinstance(event.get("external_id"), int):
                raise SchemaChangeError("distance_eval external_id invalid")
            if not isinstance(event.get("level"), int):
                raise SchemaChangeError("distance_eval level invalid")
            decode_dist_bits(event.get("dist_bits"))
        schema.setdefault(event_type, set()).update(keys)

    # A single group may legitimately omit some stop-related event types.
    # The frozen one-hot DOMAIN is five types; the observed per-file schema
    # must be a subset with exactly the frozen field set for each observed type.
    observed_schema = {e: sorted(v) for e, v in schema.items()}
    return notice, events, observed_schema


def observer_schema_digest(schemas: Iterable[dict[str, Any]]) -> str:
    merged: dict[str, set[str]] = {}
    for schema in schemas:
        for event_type, keys in schema.items():
            merged.setdefault(event_type, set()).update(keys)
    if set(merged) != ALLOWED_EVENT_TYPE_SET:
        raise SchemaChangeError("observer event-type set differs from frozen domain")
    return _canonical_json_sha({k: sorted(v) for k, v in merged.items()})


# --------------------------------------------------------------------------- #
# Feature extraction — observer-only, no paths, no internal diagnostics
# --------------------------------------------------------------------------- #
def _mean(values: Sequence[float]) -> float:
    return float(statistics.fmean(values))


def _std(values: Sequence[float]) -> float:
    # Population std over the fixed six-query bundle; ddof=0 is deterministic.
    return float(statistics.pstdev(values))


def query_feature_vector(
    query_id: int, events: Sequence[dict[str, Any]], target_label: int
) -> dict[str, float | int]:
    q_events = [e for e in events if e["query_id"] == query_id]
    indices = [e["event_index"] for e in q_events]
    if indices and indices != list(range(len(indices))):
        raise SchemaChangeError("observer event_index is not dense per query")

    counts = {event_type: 0 for event_type in ALLOWED_EVENT_TYPES}
    for event in q_events:
        counts[event["event_type"]] += 1

    target_events = [
        e for e in q_events
        if e["event_type"] == "distance_eval" and e.get("external_id") == target_label
    ]
    first_target = target_events[0] if target_events else None
    target_dist = decode_dist_bits(first_target["dist_bits"]) if first_target else -1.0
    target_level = int(first_target["level"]) if first_target else -1
    target_first = int(first_target["event_index"]) if first_target else -1
    target_last = int(target_events[-1]["event_index"]) if target_events else -1

    def stop_features(event_type: str) -> tuple[int, int, int]:
        hits = [e for e in q_events if e["event_type"] == event_type]
        return (
            1 if hits else 0,
            len(hits),
            int(hits[0]["event_index"]) if hits else -1,
        )

    stop_present, stop_count, stop_first = stop_features("stop_check")
    search_present, search_count, search_first = stop_features("search_stop")

    last_type = q_events[-1]["event_type"] if q_events else None
    last_onehot = {e: int(last_type == e) for e in ALLOWED_EVENT_TYPES}

    dist_events = [e for e in q_events if e["event_type"] == "distance_eval"]
    dist_values = [decode_dist_bits(e["dist_bits"]) for e in dist_events]
    dist_levels = [int(e["level"]) for e in dist_events]
    if dist_values:
        dist_min, dist_max, dist_mean = min(dist_values), max(dist_values), _mean(dist_values)
        level_min, level_max, level_mean = min(dist_levels), max(dist_levels), _mean(dist_levels)
    else:
        # Same out-of-domain sentinels as the frozen target-missing rule.
        dist_min = dist_max = dist_mean = -1.0
        level_min = level_max = -1
        level_mean = -1.0

    return {
        "observer_event_count": len(q_events),
        "event_count_distance_eval": counts["distance_eval"],
        "event_count_candidate_consider": counts["candidate_consider"],
        "event_count_candidate_pop": counts["candidate_pop"],
        "event_count_stop_check": counts["stop_check"],
        "event_count_search_stop": counts["search_stop"],
        "target_visible": int(bool(target_events)),
        "target_count": len(target_events),
        "target_first_index": target_first,
        "target_last_index": target_last,
        "target_dist_value": float(target_dist),
        "target_level": target_level,
        "stop_check_present": stop_present,
        "stop_check_count": stop_count,
        "stop_check_first_index": stop_first,
        "search_stop_present": search_present,
        "search_stop_count": search_count,
        "search_stop_first_index": search_first,
        **{f"last_type_{e}": last_onehot[e] for e in ALLOWED_EVENT_TYPES},
        "distance_eval_level_min": float(level_min),
        "distance_eval_level_max": float(level_max),
        "distance_eval_level_mean": float(level_mean),
        "distance_eval_dist_min": float(dist_min),
        "distance_eval_dist_max": float(dist_max),
        "distance_eval_dist_mean": float(dist_mean),
    }


def extract_bundle_features(
    observer_events: Sequence[dict[str, Any]], target_label: int
) -> dict[str, float | int]:
    """Build one bundle from observer events only. No path or private input."""
    for event in observer_events:
        keys = set(event)
        if keys & FORBIDDEN_OBS_KEYS:
            raise LeakageError("forbidden field entered feature extraction")
        event_type = event.get("event_type")
        if event_type not in ALLOWED_EVENT_TYPE_SET:
            raise SchemaChangeError(f"unknown event_type {event_type!r}")
        expected = DIST_OBS_KEYS if event_type == "distance_eval" else BASE_OBS_KEYS
        if keys != expected:
            raise SchemaChangeError("observer event schema is not frozen")

    per_query = [query_feature_vector(q, observer_events, target_label) for q in QUERY_IDS]
    out: dict[str, float | int] = {}
    for metric in PER_QUERY_METRICS:
        values = [float(q[metric]) for q in per_query]
        out[f"f__{metric}__mean"] = _mean(values)
        out[f"f__{metric}__min"] = min(values)
        out[f"f__{metric}__max"] = max(values)
        out[f"f__{metric}__std"] = _std(values)
    out[VISIBLE_QUERY_COUNT_COLUMN] = sum(int(q["target_visible"]) for q in per_query)
    if tuple(out) != FEATURE_COLUMNS:
        raise SchemaChangeError("feature columns drifted from frozen schema")
    return out


def validate_feature_row(row: dict[str, Any]) -> None:
    if tuple(row) != FEATURE_COLUMNS:
        raise SchemaChangeError("feature row columns drifted")
    for value in row.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaChangeError("feature value is not numeric")
        if value != value or value in (float("inf"), float("-inf")):
            raise SchemaChangeError("feature value is not finite")


# --------------------------------------------------------------------------- #
# Pair execution and manifests
# --------------------------------------------------------------------------- #
def _write_run_stdout(run_dir: Path, state: str, proc: subprocess.CompletedProcess) -> None:
    (run_dir / f"harness_{state}_stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (run_dir / f"harness_{state}_stderr.txt").write_text(proc.stderr, encoding="utf-8")


def run_one_pair(
    pair: DevPair,
    harness: Path,
    loader: Path,
    run_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, list[dict[str, Any]]]]]:
    run_dir = run_root / pair.pair_id
    run_dir.mkdir(parents=True, exist_ok=True)

    loader_report = verify_loader(pair, loader)
    trace_dirs: dict[str, Path] = {}
    harness_report: dict[str, Any] = {}
    for state, fixture in (("A0", pair.a0_path), ("A1", pair.a1_path)):
        outdir = run_dir / f"trace_{state}"
        proc = pd.run_harness(harness, fixture, outdir)
        _write_run_stdout(run_dir, state, proc)
        if proc.returncode != 0:
            raise TechnicalPairFailure(f"{state} harness returncode={proc.returncode}")
        if "all_results_authorized=1" not in proc.stdout:
            raise TechnicalPairFailure(f"{state} harness lost authorized-result invariant")
        trace_dirs[state] = outdir
        harness_report[state] = {
            "returncode": proc.returncode,
            "all_results_authorized": True,
            "c2_khit_seen": "c2_khit_seen=1" in proc.stdout,
        }

    observer_events: dict[str, dict[str, list[dict[str, Any]]]] = {}
    schema_by_group: dict[str, dict[str, Any]] = {}
    query_completeness: dict[str, dict[str, list[int]]] = {}
    notice_by_group: dict[str, dict[str, Any]] = {}
    for group in GROUPS:
        observer_events[group] = {}
        schema_by_group[group] = {}
        query_completeness[group] = {}
        for state in ACL_STATES:
            path = trace_dirs[state] / f"observer_proxy_{group}.jsonl"
            if not path.is_file():
                raise TechnicalPairFailure(f"missing observer proxy {state}/{group}")
            notice, events, schema = parse_observer_file(path)
            obs_qids = sorted({e["query_id"] for e in events})
            if obs_qids != list(QUERY_IDS):
                raise TechnicalPairFailure(f"incomplete queries {state}/{group}: {obs_qids}")
            observer_events[group][state] = events
            query_completeness[group][state] = obs_qids
            schema_by_group[group][state] = schema
            notice_by_group.setdefault(group, {})[state] = notice

    # Three independent target-visibility layers are recorded by the frozen
    # 3A.8 analyser, but they are NOT passed to feature extraction.
    visibility: dict[str, Any] = {}
    for group in GROUPS:
        v0, v1, _cmp = pd.analyse_group(
            group, trace_dirs["A0"], trace_dirs["A1"], TARGET_LABEL
        )
        visibility[group] = {
            "A0": {
                "internal_distance_eval": v0.internal_distance_eval,
                "internal_filter_check": v0.internal_filter_check,
                "observer_visible": v0.observer_visible,
            },
            "A1": {
                "internal_distance_eval": v1.internal_distance_eval,
                "internal_filter_check": v1.internal_filter_check,
                "observer_visible": v1.observer_visible,
            },
        }

    schema_digest = observer_schema_digest(
        schema_by_group[g][s] for g in GROUPS for s in ACL_STATES
    )
    structure = {
        "pair": pair.safe_summary(),
        "invariant": pair.invariant(),
        "cpp_loader": loader_report,
        "harness": harness_report,
        "query_completeness": query_completeness,
        "observer_notice": notice_by_group,
        "observer_schema_sha256": schema_digest,
        "target_visibility": visibility,
    }
    write_json(run_dir / "structure_summary.json", structure)
    return structure, observer_events


def environment_manifest(harness: Path, loader: Path, compiler_version: str) -> dict[str, Any]:
    tracked_paths = [
        PROTOCOL_PATH,
        MODULE_3A4 / "acl_bitmap.py",
        MODULE_3A4 / "acl_bitmap.h",
        MODULE_3A4 / "hnsw_acl_filter.h",
        MODULE_3A4 / "test_acl_bitmap.cpp",
        HARNESS_DIR / "main.cpp",
        PAIR_DIR / "pair_driver.py",
        RM2_INCLUDE / "hnswalg.h",
        RM2_INCLUDE / "hnswlib.h",
        RM2_INCLUDE / "space_ip.h",
        RM2_INCLUDE / "rm2_sink.h",
    ]
    blobs: dict[str, Any] = {}
    for path in tracked_paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", rel],
            capture_output=True, text=True,
        )
        blob = proc.stdout.split()[1] if proc.stdout.strip() else None
        blobs[rel] = {"git_blob_sha1": blob, "sha256": _sha256_file(path)}

    head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {
        "repo_head_commit": head,
        "frozen_code": blobs,
        "harness_binary_path_private": str(harness),
        "loader_binary_path_private": str(loader),
        "compiler_version": compiler_version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
    }


def run_pipeline(
    private_root: Path,
    target_pairs: int = 125,
    max_attempts: int | None = None,
    *,
    allow_small_run: bool = False,
) -> dict[str, Any]:
    if target_pairs < 125 and not allow_small_run:
        raise Dev1Stop("DEV-1 formal run requires at least 125 valid pairs")
    private = assert_private_root(private_root)
    constants = validate_frozen_constants()
    if max_attempts is None:
        max_attempts = target_pairs * 10

    work = private / "work"
    runs_root = private / "runs"
    features_dir = private / "features"
    logs_dir = private / "logs"
    for d in (work, runs_root, features_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)
    harness, loader, compiler_version = compile_tools(work)
    env = environment_manifest(harness, loader, compiler_version)

    feature_headers = list(FEATURE_COLUMNS) + [LABEL_COLUMN]
    feature_writers: dict[str, Any] = {}
    grouping_writers: dict[str, Any] = {}
    feature_files: dict[str, Path] = {}
    grouping_files: dict[str, Path] = {}
    for group in GROUPS:
        feature_files[group] = features_dir / f"{group}_features.csv"
        grouping_files[group] = features_dir / f"{group}_grouping_private.csv"
        feature_writers[group] = feature_files[group].open("w", newline="", encoding="utf-8")
        grouping_writers[group] = grouping_files[group].open("w", newline="", encoding="utf-8")
        csv.writer(feature_writers[group]).writerow(feature_headers)
        csv.writer(grouping_writers[group]).writerow(
            ["row_index", "pair_id", "acl_state", "label"]
        )

    manifest: dict[str, Any] = {
        "stage": "H1-RM.3A.10 DEV-1",
        "namespace": NAMESPACE,
        "constants": constants,
        "environment": env,
        "feature_schema": {
            "columns": list(feature_headers),
            "feature_dim": FEATURE_DIM,
            "columns_sha256": _canonical_json_sha(feature_headers),
            "aggregations": list(AGGREGATIONS),
            "std_ddof": 0,
        },
        "pairs": [],
        "failures": [],
    }

    valid = 0
    attempts = 0
    started = time.time()
    manifest["run_timestamps"] = {
        "started_epoch": started,
        "started_local": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
    }
    try:
        while valid < target_pairs and attempts < max_attempts:
            attempts += 1
            pair_id = f"DEV-{attempts:06d}"
            try:
                pair_dir = runs_root / pair_id
                pair = build_dev_pair(pair_dir, pair_id)
                structure, observer_events = run_one_pair(pair, harness, loader, runs_root)
                bundle_rows: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
                for group in GROUPS:
                    for state in ACL_STATES:
                        bundle = extract_bundle_features(
                            observer_events[group][state], TARGET_LABEL
                        )
                        validate_feature_row(bundle)
                        bundle_rows[group].append(bundle)

                # Only after every structural and feature check succeeds do we
                # commit this pair to the private datasets and manifest.
                for group in GROUPS:
                    writer = csv.writer(feature_writers[group])
                    group_writer = csv.writer(grouping_writers[group])
                    for state, row in zip(ACL_STATES, bundle_rows[group]):
                        row_index = valid * 2 + ACL_STATES.index(state)
                        writer.writerow([
                            LABEL_MAP[state] if c == LABEL_COLUMN else row[c]
                            for c in feature_headers
                        ])
                        group_writer.writerow(
                            [row_index, pair_id, state, LABEL_MAP[state]]
                        )
                manifest["pairs"].append(structure)
                valid += 1
            except (StructuralPairFailure, TechnicalPairFailure) as exc:
                fail_dir = runs_root / pair_id / "failure.json"
                fail_dir.parent.mkdir(parents=True, exist_ok=True)
                write_json(fail_dir, {
                    "pair_id": pair_id,
                    "stage": type(exc).__name__,
                    "reason": str(exc),
                    "timestamp": time.time(),
                })
                manifest["failures"].append({
                    "pair_id": pair_id,
                    "type": type(exc).__name__,
                    "reason": str(exc),
                })
                continue

        if valid < target_pairs:
            raise Dev1Stop(
                f"only {valid}/{target_pairs} valid pairs after {attempts} attempts"
            )

        finished = time.time()
        manifest["run_timestamps"].update({
            "finished_epoch": finished,
            "finished_local": time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(finished)
            ),
        })
        manifest["summary"] = {
            "valid_pairs": valid,
            "attempted_pairs": attempts,
            "technical_or_structural_failures": len(manifest["failures"]),
            "rows_per_group": valid * 2,
            "elapsed_seconds": round(finished - started, 3),
            "feature_files": {g: str(p) for g, p in feature_files.items()},
            "grouping_files_private": {g: str(p) for g, p in grouping_files.items()},
        }
        write_json(private / "manifest.json", manifest)
        return {
            "private_root": str(private),
            "valid_pairs": valid,
            "attempted_pairs": attempts,
            "failures": len(manifest["failures"]),
            "feature_dim": FEATURE_DIM,
            "feature_columns_sha256": FEATURE_SCHEMA_SHA,
            "manifest": str(private / "manifest.json"),
        }
    finally:
        for fh in list(feature_writers.values()) + list(grouping_writers.values()):
            fh.close()


LABEL_MAP = {"A0": 0, "A1": 1}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--pairs", type=int, default=125)
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument(
        "--allow-small-run",
        action="store_true",
        help="pipeline smoke only; never use for formal DEV-1 admission",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_pipeline(
            args.private_root,
            args.pairs,
            args.max_attempts,
            allow_small_run=args.allow_small_run,
        )
    except Dev1Stop as exc:
        print(f"DEV1 STOP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
