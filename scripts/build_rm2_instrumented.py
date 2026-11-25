#!/usr/bin/env python3
"""Generate the H1-RM.2 observation-only instrumented hnswlib v0.9.0 snapshot.

Inputs (read-only):
  third_party/hnswlib-v0.9.0/hnswlib/*        pristine CRLF snapshot pinned at d9b3608c

Outputs (new files only):
  third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/*
  patches/hnswlib-v0.9.0-rm2-stop-semantics.patch

Every inserted site is wrapped in HNSWLIB_RM2_TRACE_ENABLED and is a pure
observation call RM2_EV(...); no branch, candidate-selection, result-set,
lowerBound update or stop logic is changed. When the macro is undefined the
header is byte-identical in behaviour to pristine v0.9.0.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "third_party" / "hnswlib-v0.9.0" / "hnswlib"
DST = ROOT / "third_party" / "hnswlib-v0.9.0-rm2-instrumented" / "hnswlib"
PATCH = ROOT / "patches" / "hnswlib-v0.9.0-rm2-stop-semantics.patch"

SINK = r'''#pragma once

// H1-RM.2 observation-only instrumentation interface.
// Included by the instrumented hnswalg.h ONLY when HNSWLIB_RM2_TRACE_ENABLED
// is defined. The harness in experiments/h1_rm2_native_stop/main.cpp defines
// the globals and the emitter. No distance formula is reimplemented.

#include <cstdint>
#include "hnswlib.h"

extern uint64_t g_rm2_current_query_id;
extern bool g_rm2_enabled;

extern void rm2_emit(const char *event_type,
                     uint64_t internal_id,
                     uint64_t external_id,
                     int level,
                     float dist,
                     int64_t extra);
'''

# Each (name, old, new, expected_count). old must match exactly once unless
# expected_count states otherwise. New only ADDS RM2_EV(...) observation calls.
SITES: list[tuple[str, str, str, int]] = [
    (
        "include-and-macro",
        "#include <memory>\r\n\r\nnamespace hnswlib {",
        "#include <memory>\r\n\r\n"
        "#ifdef HNSWLIB_RM2_TRACE_ENABLED\r\n"
        '#include "rm2_sink.h"\r\n'
        "#define RM2_EV(ev, iid, lvl, d, extra)                                    \\\r\n"
        "    do {                                                                   \\\r\n"
        "        if (g_rm2_enabled) {                                               \\\r\n"
        "            rm2_emit((const char *)(ev), (uint64_t)(iid),                  \\\r\n"
        "                     (uint64_t)getExternalLabel((iid)), (int)(lvl),        \\\r\n"
        "                     (float)(d), (int64_t)(extra));                        \\\r\n"
        "        }                                                                  \\\r\n"
        "    } while (0)\r\n"
        "#else\r\n"
        "#define RM2_EV(ev, iid, lvl, d, extra) do {} while (0)\r\n"
        "#endif\r\n\r\n"
        "namespace hnswlib {",
        1,
    ),
    (
        "searchBaseLayerST-entrypoint-distance",
        "            char* ep_data = getDataByInternalId(ep_id);\r\n"
        "            dist_t dist = fstdistfunc_(data_point, ep_data, dist_func_param_);\r\n"
        "            lowerBound = dist;",
        "            char* ep_data = getDataByInternalId(ep_id);\r\n"
        "            dist_t dist = fstdistfunc_(data_point, ep_data, dist_func_param_);\r\n"
        '            RM2_EV("distance_eval", ep_id, 0, dist, 1);\r\n'
        "            lowerBound = dist;",
        1,
    ),
    (
        "searchBaseLayerST-entrypoint-result-add",
        "            top_candidates.emplace(dist, ep_id);\r\n"
        "            if (!bare_bone_search && stop_condition) {",
        "            top_candidates.emplace(dist, ep_id);\r\n"
        '            RM2_EV("result_add", ep_id, 0, dist, 1);\r\n'
        "            if (!bare_bone_search && stop_condition) {",
        1,
    ),
    (
        "searchBaseLayerST-stop-check",
        "            if (flag_stop_search) {\r\n"
        "                break;\r\n"
        "            }",
        "            RM2_EV(\"stop_check\", current_node_pair.second, 0, candidate_dist,\r\n"
        "                   flag_stop_search ? 1 : 0);\r\n"
        "            if (flag_stop_search) {\r\n"
        '                RM2_EV("search_stop", current_node_pair.second, 0, candidate_dist, 0);\r\n'
        "                break;\r\n"
        "            }",
        1,
    ),
    (
        "searchBaseLayerST-candidate-pop",
        "            candidate_set.pop();\r\n\r\n"
        "            tableint current_node_id = current_node_pair.second;",
        "            candidate_set.pop();\r\n"
        '            RM2_EV("candidate_pop", current_node_pair.second, 0, candidate_dist, 0);\r\n\r\n'
        "            tableint current_node_id = current_node_pair.second;",
        1,
    ),
    (
        "searchBaseLayerST-level0-distance",
        "                    char *currObj1 = (getDataByInternalId(candidate_id));\r\n"
        "                    dist_t dist = fstdistfunc_(data_point, currObj1, dist_func_param_);\r\n\r\n"
        "                    bool flag_consider_candidate;",
        "                    char *currObj1 = (getDataByInternalId(candidate_id));\r\n"
        "                    dist_t dist = fstdistfunc_(data_point, currObj1, dist_func_param_);\r\n"
        '                    RM2_EV("distance_eval", candidate_id, 0, dist, 0);\r\n\r\n'
        "                    bool flag_consider_candidate;",
        1,
    ),
    (
        "searchBaseLayerST-candidate-consider",
        "                    if (flag_consider_candidate) {\r\n"
        "                        candidate_set.emplace(-dist, candidate_id);",
        "                    RM2_EV(\"candidate_consider\", candidate_id, 0, dist,\r\n"
        "                           flag_consider_candidate ? 1 : 0);\r\n"
        "                    if (flag_consider_candidate) {\r\n"
        "                        candidate_set.emplace(-dist, candidate_id);",
        1,
    ),
    (
        "searchBaseLayerST-result-add-candidate",
        "                            top_candidates.emplace(dist, candidate_id);\r\n"
        "                            if (!bare_bone_search && stop_condition) {",
        "                            top_candidates.emplace(dist, candidate_id);\r\n"
        '                            RM2_EV("result_add", candidate_id, 0, dist, 0);\r\n'
        "                            if (!bare_bone_search && stop_condition) {",
        1,
    ),
    (
        "searchBaseLayerST-result-remove",
        "                            tableint id = top_candidates.top().second;\r\n"
        "                            top_candidates.pop();\r\n"
        "                            if (!bare_bone_search && stop_condition) {",
        "                            tableint id = top_candidates.top().second;\r\n"
        "                            top_candidates.pop();\r\n"
        '                            RM2_EV("result_remove", id, 0, dist, 0);\r\n'
        "                            if (!bare_bone_search && stop_condition) {",
        1,
    ),
    (
        "search-entrypoint-distance",
        "        tableint currObj = enterpoint_node_;\r\n"
        "        dist_t curdist = fstdistfunc_(query_data, getDataByInternalId(enterpoint_node_), dist_func_param_);\r\n\r\n"
        "        for (int level = maxlevel_; level > 0; level--) {",
        "        tableint currObj = enterpoint_node_;\r\n"
        "        dist_t curdist = fstdistfunc_(query_data, getDataByInternalId(enterpoint_node_), dist_func_param_);\r\n"
        '        RM2_EV("distance_eval", enterpoint_node_, maxlevel_, curdist, 2);\r\n\r\n'
        "        for (int level = maxlevel_; level > 0; level--) {",
        2,  # searchKnn + searchStopConditionClosest (identical body)
    ),
    (
        "search-upper-distance",
        "                    dist_t d = fstdistfunc_(query_data, getDataByInternalId(cand), dist_func_param_);\r\n\r\n"
        "                    if (d < curdist) {",
        "                    dist_t d = fstdistfunc_(query_data, getDataByInternalId(cand), dist_func_param_);\r\n"
        '                    RM2_EV("distance_eval", cand, level, d, 3);\r\n\r\n'
        "                    if (d < curdist) {",
        2,  # searchKnn + searchStopConditionClosest
    ),
]

HEADER_FILES = [
    "bruteforce.h", "hnswalg.h", "hnswlib.h", "space_ip.h",
    "space_l2.h", "stop_condition.h", "visited_list_pool.h",
]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    src_alg = (SRC / "hnswalg.h").read_bytes()
    text = src_alg.decode("utf-8")
    for name, old, new, count in SITES:
        found = text.count(old)
        if found != count:
            print(f"ABORT site {name!r}: expected {count} matches, found {found}", file=sys.stderr)
            return 2
        text = text.replace(old, new)
    out_alg = text.encode("utf-8")

    DST.mkdir(parents=True, exist_ok=True)
    for fn in HEADER_FILES:
        data = out_alg if fn == "hnswalg.h" else (SRC / fn).read_bytes()
        (DST / fn).write_bytes(data)
    (DST / "rm2_sink.h").write_bytes(SINK.encode("utf-8"))

    # unified diff (LF-normalised for readability; the snapshot itself is CRLF)
    import difflib
    a = src_alg.decode("utf-8").splitlines()
    b = out_alg.decode("utf-8").splitlines()
    diff = "\n".join(difflib.unified_diff(
        a, b, fromfile="a/hnswlib/hnswalg.h", tofile="b/hnswlib/hnswalg.h", lineterm="",
    )) + "\n"
    diff += "--- /dev/null\n+++ b/hnswlib/rm2_sink.h\n"
    diff += "".join("+" + ln + "\n" for ln in SINK.splitlines())
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_bytes(("H1-RM.2 observation-only instrumentation (generated by "
                       "scripts/build_rm2_instrumented.py)\n" + diff).encode("utf-8"))

    print("pristine_hnswalg_sha256=" + sha256(src_alg))
    print("rm2_hnswalg_sha256=" + sha256(out_alg))
    print("rm2_sink_sha256=" + sha256(SINK.encode("utf-8")))
    print("sites=" + str(len(SITES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
