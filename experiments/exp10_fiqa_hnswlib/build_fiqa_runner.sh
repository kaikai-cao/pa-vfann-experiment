#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/experiments/exp10_fiqa_hnswlib/fiqa_trace_runner.cpp"
INC="$ROOT/third_party/hnswlib-v0.9.0-instrumented/hnswlib"
OUT_DIR="$ROOT/build"
OUT="$OUT_DIR/exp10_fiqa_trace_runner.exe"

mkdir -p "$OUT_DIR"

g++ -std=c++17 -O2 -Wall -Wextra -pthread \
    -DHNSWLIB_TRACE_ENABLED=1 \
    -I"$INC" \
    "$SRC" -o "$OUT"

echo "built=$OUT"
