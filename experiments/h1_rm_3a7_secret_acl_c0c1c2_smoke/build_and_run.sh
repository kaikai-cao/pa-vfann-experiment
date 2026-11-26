#!/usr/bin/env bash
# H1-RM.3A.7 — reproducible build + run of the C0/C1/C2 private-ACL smoke.
#
# Usage: build_and_run.sh <fixture_path> <outdir> [output_exe]
#
# The fixture MUST be a fixed synthetic vector produced by the existing
# Python encode_acl_bitmap(). It is not a real ACL instance.
# Requires the RM2-instrumented hnswlib headers and the trace macro ON.

set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "usage: $0 <fixture_path> <outdir> [output_exe]" >&2
    exit 2
fi

FIXTURE="$1"
OUTDIR="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MODULE_3A4="$REPO_ROOT/experiments/h1_rm_3a4_secret_acl"
RM2="$REPO_ROOT/third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib"
EXE="${3:-$HERE/h1rm3a7_smoke}"

CXX="${CXX:-g++}"
if ! command -v "$CXX" >/dev/null 2>&1; then
    CXX="$(command -v clang++ || true)"
fi
if [ -z "$CXX" ]; then
    echo "ENVIRONMENT BLOCK: no C++ compiler" >&2
    exit 2
fi

mkdir -p "$OUTDIR"
"$CXX" -std=c++17 -O2 -Wall -Wextra -DHNSWLIB_RM2_TRACE_ENABLED=1 \
    -I"$MODULE_3A4" -I"$HERE" -I"$RM2" \
    "$HERE/main.cpp" -o "$EXE"

"$EXE" "$FIXTURE" "$OUTDIR"
