#!/usr/bin/env bash
# H1-RM.2 build + run. Called from Git Bash; g++ is MinGW-W64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="$ROOT/experiments/h1_rm2_native_stop"
PRISTINE="$ROOT/third_party/hnswlib-v0.9.0/hnswlib"
RM2="$ROOT/third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib"
BUILD="$ROOT/build/h1_rm2"
TRACE_OUT="$ROOT/results/h1_rm2/trace_on"
OFF_OUT="$ROOT/results/h1_rm2/trace_off"
UP_OUT="$ROOT/results/h1_rm2/upstream"
mkdir -p "$BUILD" "$TRACE_OUT" "$OFF_OUT" "$UP_OUT"

GXX=g++
COMMON=(-std=c++17 -O2 -Wall -Wextra)

echo "[1/4] compile upstream (no trace macros, no events)"
"$GXX" "${COMMON[@]}" -I"$PROBE" -I"$PRISTINE" \
  "$PROBE/main.cpp" -o "$BUILD/h1rm2_upstream.exe"

echo "[2/4] compile instrumented (trace macros on)"
"$GXX" "${COMMON[@]}" -DHNSWLIB_RM2_TRACE_ENABLED=1 -I"$PROBE" -I"$RM2" \
  "$PROBE/main.cpp" -o "$BUILD/h1rm2_instrumented.exe"

echo "[3/5] run pristine upstream (no instrumentation at all, trace=0)"
"$BUILD/h1rm2_upstream.exe" "$UP_OUT" 0

echo "[4/5] run instrumented with trace=1 (C0/C1/C2 events)"
"$BUILD/h1rm2_instrumented.exe" "$TRACE_OUT" 1

echo "[5/5] run instrumented with trace=0 (sink-off top-k sanity)"
"$BUILD/h1rm2_instrumented.exe" "$OFF_OUT" 0

echo "DONE"
