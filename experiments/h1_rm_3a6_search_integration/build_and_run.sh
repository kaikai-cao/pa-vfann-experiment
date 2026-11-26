#!/usr/bin/env bash
# H1-RM.3A.6 — reproducible build + run of the minimal real-search check.
#
# Usage:
#   build_and_run.sh <hnswlib_include_dir> <fixture_path> [output_exe]
#
# Example include dirs (relative to repository root):
#   third_party/hnswlib-v0.9.0/hnswlib
#   third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib
#
# The fixture MUST be a fixed synthetic vector produced by the existing
# Python encode_acl_bitmap(). No real ACL fixture is used here.

set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "usage: $0 <hnswlib_include_dir> <fixture_path> [output_exe]" >&2
    exit 2
fi

HNSW_INC="$1"
FIXTURE="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MODULE_3A4="$REPO_ROOT/experiments/h1_rm_3a4_secret_acl"
OUT="${3:-$HERE/h1_rm3a6_search}"

CXX="${CXX:-g++}"
if ! command -v "$CXX" >/dev/null 2>&1; then
    CXX="$(command -v clang++ || true)"
fi
if [ -z "$CXX" ]; then
    echo "ENVIRONMENT BLOCK: no C++ compiler" >&2
    exit 2
fi

"$CXX" -std=c++17 -Wall -Wextra -O0 \
    -I"$MODULE_3A4" -I"$HERE" -I"$HNSW_INC" \
    "$HERE/main.cpp" -o "$OUT"

"$OUT" "$FIXTURE"
