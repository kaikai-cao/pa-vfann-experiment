"""Tests 6 and 7: E3 policy independence and EXP-02 immutability."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pa_vfann_exp02a.config import ROOT


def test_6_e3_search_trace_still_policy_independent(small_exp02_env):
    from pa_vfann_exp02.algorithms import derive, run_log

    cfg, dataset, graph, p1, p2 = small_exp02_env
    query = dataset.query_vectors[0]
    budget = 100
    log_a = run_log(query, dataset.vectors, graph, cfg, "E3_FIXED_TRACE",
                    max_expansions=budget)
    log_b = run_log(query, dataset.vectors, graph, cfg, "E3_FIXED_TRACE",
                    max_expansions=budget)
    assert log_a.discovery_sequence == log_b.discovery_sequence
    assert log_a.visit_sequence == log_b.visit_sequence
    assert log_a.expansion_sequence == log_b.expansion_sequence
    assert log_a.distances == log_b.distances

    oa = derive(log_a, cfg, budget, policy_mask=p1.mask)
    ob = derive(log_b, cfg, budget, policy_mask=p2.mask)
    assert oa.discovery_sequence == ob.discovery_sequence
    assert oa.visit_sequence == ob.visit_sequence
    assert oa.expansion_sequence == ob.expansion_sequence
    assert oa.candidate_count == ob.candidate_count
    assert oa.policy_dependent is False and ob.policy_dependent is False

    # run_log strips a mask for E3; the hard refusal lives in traverse().
    from pa_vfann_exp02.lazy_search import traverse

    with pytest.raises(ValueError, match="must not receive a policy mask"):
        traverse(query, dataset.vectors, graph, log_a.entry_node, budget,
                 mode="E3", policy_mask=p1.mask)


def test_7_exp02_raw_csv_and_code_unmodified():
    path = ROOT / "exp02a" / "audit" / "exp02_baseline_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["baseline_commit"] == "29ec958241a05ad6a2a419442d3e322a6abd9892"
    assert manifest["file_count"] == len(manifest["files"]) > 40
    for rel, meta in manifest["files"].items():
        target = ROOT / rel
        assert target.exists(), f"missing baseline file: {rel}"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == meta["sha256"], f"baseline file changed: {rel}"
        assert target.stat().st_size == meta["bytes"], f"baseline size changed: {rel}"

    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", "exp02"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert status.stdout.strip() == "", "tracked EXP-02 files have local changes"
