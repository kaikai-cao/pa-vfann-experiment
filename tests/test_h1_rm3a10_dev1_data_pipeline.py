"""H1-RM.3A.10 — DEV-1 data pipeline tests.

Tests only structural correctness, observer-only feature extraction and private
artifact isolation. No classifier, no C selection, no BA/AUC, no PILOT/CONFIRM.

Run:
    python -m pytest tests/test_h1_rm3a10_dev1_data_pipeline.py -v
"""

from __future__ import annotations

import csv
import json
import statistics
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV1_DIR = REPO_ROOT / "experiments" / "h1_rm_3a10_dev1_data_pipeline"
if str(DEV1_DIR) not in sys.path:
    sys.path.insert(0, str(DEV1_DIR))

import dev1_pipeline as dp  # noqa: E402


def dist_bits(value: float) -> str:
    raw = struct.unpack("<I", struct.pack("<f", value))[0]
    return f"0x{raw:08x}"


def obs_event(query_id: int, index: int, event_type: str, **extra) -> dict:
    event = {
        "query_id": query_id,
        "event_index": index,
        "group": "C0",
        "event_type": event_type,
    }
    event.update(extra)
    return event


def distance_event(query_id: int, index: int, label: int, value: float) -> dict:
    return obs_event(
        query_id,
        index,
        "distance_eval",
        external_id=label,
        level=0,
        dist_bits=dist_bits(value),
    )


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory):
    """Two REAL small pairs, explicitly not formal DEV data."""
    private = tmp_path_factory.mktemp("dev1_pipeline_small")
    result = dp.run_pipeline(
        private, target_pairs=2, max_attempts=2, allow_small_run=True
    )
    manifest = json.loads((Path(private) / "manifest.json").read_text(encoding="utf-8"))
    return {"private": Path(private), "result": result, "manifest": manifest}


def test_01_target_and_pair_invariant(pipeline_run):
    for item in pipeline_run["manifest"]["pairs"]:
        inv = item["invariant"]
        assert all(inv.values())
        assert item["pair"]["target"] == dp.TARGET_INDEX == 103
        assert item["pair"]["target_label"] == dp.TARGET_LABEL == 101751
        assert item["pair"]["diff"] == [103]


def test_02_base_acls_are_independently_generated(tmp_path):
    digests = []
    for i in range(5):
        pair = dp.build_dev_pair(tmp_path / f"pair_{i}", f"TEST-{i:06d}")
        digests.append(pair.base_digest)
        assert pair.diff == (dp.TARGET_INDEX,)
    assert len(set(digests)) == 5


def test_03_cpp_loader_verifies_generated_acls(tmp_path, pipeline_run):
    loader = Path(pipeline_run["manifest"]["environment"]["loader_binary_path_private"])
    pair = dp.build_dev_pair(tmp_path / "loader_pair", "TEST-LOADER")
    report = dp.verify_loader(pair, loader)
    assert report["A0"]["load"] == "OK"
    assert report["A1"]["load"] == "OK"
    assert report["A0"]["target_bit"] == 0
    assert report["A1"]["target_bit"] == 1
    assert report["A0"]["all_queried_bits_match"] is True
    assert report["A1"]["all_queried_bits_match"] is True


def test_04_each_pair_runs_all_groups_for_both_states(pipeline_run):
    for item in pipeline_run["manifest"]["pairs"]:
        assert set(item["harness"]) == set(dp.ACL_STATES)
        for state in dp.ACL_STATES:
            assert item["harness"][state]["returncode"] == 0
            assert item["harness"][state]["all_results_authorized"] is True
        for group in dp.GROUPS:
            assert set(item["query_completeness"][group]) == set(dp.ACL_STATES)

    for group in dp.GROUPS:
        path = pipeline_run["private"] / "features" / f"{group}_features.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 4  # 2 pairs x A0/A1


def test_05_six_queries_are_complete(pipeline_run):
    for item in pipeline_run["manifest"]["pairs"]:
        for group in dp.GROUPS:
            for state in dp.ACL_STATES:
                assert item["query_completeness"][group][state] == list(range(6))


def test_06_observer_schema_matches_frozen_whitelist(pipeline_run):
    schemas = []
    for item in pipeline_run["manifest"]["pairs"]:
        pair_id = item["pair"]["pair_id"]
        for state in dp.ACL_STATES:
            for group in dp.GROUPS:
                path = (
                    pipeline_run["private"] / "runs" / pair_id
                    / f"trace_{state}" / f"observer_proxy_{group}.jsonl"
                )
                notice, events, schema = dp.parse_observer_file(path)
                assert notice["is_physical_page_trace"] is False
                assert events
                assert set(schema).issubset(dp.ALLOWED_EVENT_TYPE_SET)
                for event_type, fields in schema.items():
                    expected = (
                        dp.DIST_OBS_KEYS if event_type == "distance_eval"
                        else dp.BASE_OBS_KEYS
                    )
                    assert set(fields) == set(expected)
                schemas.append(schema)
    digest = dp.observer_schema_digest(schemas)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_07_internal_diagnostics_cannot_enter_feature_extractor():
    import inspect

    params = set(inspect.signature(dp.extract_bundle_features).parameters)
    assert "observer_events" in params
    assert not any("internal" in p or "path" in p for p in params)

    bad_events = [
        obs_event(0, 0, "candidate_consider", extra=1),
    ]
    with pytest.raises(dp.LeakageError):
        dp.extract_bundle_features(bad_events, dp.TARGET_LABEL)

    internal_only = [obs_event(0, 0, "filter_check")]
    with pytest.raises(dp.SchemaChangeError):
        dp.extract_bundle_features(internal_only, dp.TARGET_LABEL)


def test_08_pair_id_is_not_a_feature(pipeline_run):
    for group in dp.GROUPS:
        path = pipeline_run["private"] / "features" / f"{group}_features.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
        assert "pair_id" not in header
        assert not any("pair" in col.lower() for col in header)
        assert dp.LABEL_COLUMN in header

    grouping = pipeline_run["private"] / "features" / "C0_grouping_private.csv"
    with grouping.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(row["pair_id"].startswith("DEV-") for row in rows)


def test_09_target_unseen_bundle_is_kept_with_sentinels():
    events = [distance_event(q, 0, 101768, 0.25) for q in range(6)]
    row = dp.extract_bundle_features(events, dp.TARGET_LABEL)
    assert row[dp.VISIBLE_QUERY_COUNT_COLUMN] == 0
    for agg in ("mean", "min", "max"):
        assert row[f"f__target_dist_value__{agg}"] == -1.0
        assert row[f"f__target_level__{agg}"] == -1
        assert row[f"f__target_first_index__{agg}"] == -1
        assert row[f"f__target_last_index__{agg}"] == -1
    # A constant sentinel sequence has zero dispersion by construction.
    for metric in ("target_dist_value", "target_level",
                   "target_first_index", "target_last_index"):
        assert row[f"f__{metric}__std"] == 0.0


def test_10_sentinel_values_match_frozen_protocol():
    events = [distance_event(0, 0, 101768, 0.5)]
    q = dp.query_feature_vector(1, events, dp.TARGET_LABEL)
    assert q["target_dist_value"] == -1.0
    assert q["target_level"] == -1
    assert q["target_first_index"] == -1
    assert q["target_last_index"] == -1

    seen = [distance_event(0, 0, dp.TARGET_LABEL, -0.5)]
    q = dp.query_feature_vector(0, seen, dp.TARGET_LABEL)
    assert q["target_dist_value"] == -0.5
    assert q["target_first_index"] == 0
    assert q["target_last_index"] == 0


def test_11_six_query_aggregation_is_mean_min_max_std_only():
    counts = [1, 2, 3, 4, 5, 6]
    events = []
    for q, n in enumerate(counts):
        for idx in range(n):
            events.append(obs_event(q, idx, "candidate_consider"))
    row = dp.extract_bundle_features(events, dp.TARGET_LABEL)
    assert not any(col.endswith("__sum") for col in dp.FEATURE_COLUMNS)
    assert row["f__observer_event_count__mean"] == statistics.fmean(counts)
    assert row["f__observer_event_count__min"] == min(counts)
    assert row["f__observer_event_count__max"] == max(counts)
    assert row["f__observer_event_count__std"] == statistics.pstdev(counts)


def test_12_new_event_type_triggers_schema_change_stop():
    events = [obs_event(0, 0, "future_event")]
    with pytest.raises(dp.SchemaChangeError):
        dp.extract_bundle_features(events, dp.TARGET_LABEL)


def test_13_private_artifacts_do_not_enter_repository():
    with pytest.raises(dp.Dev1Stop):
        dp.assert_private_root(REPO_ROOT / "illegal_private_dir")
    assert not (REPO_ROOT / "illegal_private_dir").exists()

    status = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    changed_files = [line[3:] for line in status if len(line) >= 4]
    forbidden_suffixes = (".bin", ".jsonl", "_features.csv", "_grouping_private.csv")
    assert not [
        f for f in changed_files
        if f.endswith(forbidden_suffixes) or f.endswith("manifest.json")
    ]
    for scope in (DEV1_DIR, REPO_ROOT / "tests" / "test_h1_rm3a10_dev1_data_pipeline.py"):
        for name in ("acl_A0.bin", "acl_A1.bin", "manifest.json"):
            if scope.is_dir():
                assert not list(scope.rglob(name))
            else:
                assert scope.name != name


def test_14_feature_dimension_and_columns_are_consistent(pipeline_run):
    expected_header = list(dp.FEATURE_COLUMNS) + [dp.LABEL_COLUMN]
    assert dp.FEATURE_DIM == 117
    headers = []
    for group in dp.GROUPS:
        path = pipeline_run["private"] / "features" / f"{group}_features.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            rows = list(reader)
        headers.append(header)
        assert header == expected_header
        assert all(len(row) == len(expected_header) for row in rows)
        assert all(row[-1] in {"0", "1"} for row in rows)
    assert headers[0] == headers[1] == headers[2]


def test_15_dist_bits_decoding_uses_frozen_3a7_bit_pattern():
    for value in (0.0, -0.5, 1.25, 3.5):
        assert dp.decode_dist_bits(dist_bits(value)) == pytest.approx(value)
