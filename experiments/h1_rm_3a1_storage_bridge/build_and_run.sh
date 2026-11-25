#!/usr/bin/env bash
# H1-RM.3A.1 storage access bridge: build + run + compare.
# Called from Git Bash; g++ is MinGW-W64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="$ROOT/experiments/h1_rm_3a1_storage_bridge"
BRIDGE_H="$PROBE/hnswlib_bridge"
PRISTINE="$ROOT/third_party/hnswlib-v0.9.0/hnswlib"
BUILD="$ROOT/build/h1_rm_3a1"
OUT="$ROOT/results/h1_rm_3a1"
BASE_OUT="$OUT/baseline"
BRIDGE_OUT="$OUT/bridged"
mkdir -p "$BUILD" "$BASE_OUT" "$BRIDGE_OUT"

GXX=g++
COMMON=(-std=c++17 -O2 -Wall -Wextra)

echo "[1/7] compile upstream (pristine headers, no trace, no bridge)"
"$GXX" "${COMMON[@]}" -I"$PROBE" -I"$PRISTINE" \
  "$PROBE/main.cpp" -o "$BUILD/h1rm31_upstream.exe"

echo "[2/7] compile instrumented+bridge (runtime switch bridge=0|1)"
"$GXX" "${COMMON[@]}" -DHNSWLIB_RM2_TRACE_ENABLED=1 -DHNSWLIB_RM31_BRIDGE=1 \
  -I"$PROBE" -I"$BRIDGE_H" \
  "$PROBE/main.cpp" -o "$BUILD/h1rm31_bridge.exe"

echo "[3/7] baseline: instrumented, storage NOT injected (bridge=0)"
"$BUILD/h1rm31_bridge.exe" "$BASE_OUT" 1 0

echo "[4/7] bridged: instrumented, storage injected (bridge=1)"
"$BUILD/h1rm31_bridge.exe" "$BRIDGE_OUT" 1 1

echo "[5/7] compare events/topk byte-for-byte and analyze request trace"
python "$PROBE/compare.py" "$ROOT"

echo "[6/7] create committed audit subsets and raw hashes"
python "$PROBE/make_audit_subset.py" "$ROOT"

echo "[7/7] build manifest"
python "$PROBE/make_manifest.py" "$ROOT"

echo "DONE"
