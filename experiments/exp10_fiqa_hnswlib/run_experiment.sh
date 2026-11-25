#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/.venv/Scripts/python"
RUNNER="$ROOT/build/exp10_fiqa_trace_runner.exe"
EMB="$ROOT/data/exp10_fiqa_embeddings"
RAW="$ROOT/results/raw"

cd "$ROOT"

echo "[step] build runner"
bash experiments/exp10_fiqa_hnswlib/build_fiqa_runner.sh

echo "[step] exact GT and masks"
"$PY" experiments/exp10_fiqa_hnswlib/prepare_ground_truth_and_masks.py

echo "[step] full hnswlib trace run"
mkdir -p "$RAW"
"$RUNNER" full "$RAW" \
  "$EMB/corpus.f32" "$EMB/test_queries.f32" \
  "$EMB/corpus_ids.txt" "$EMB/test_query_ids.txt"

echo "[step] analysis, figures and bootstrap"
"$PY" experiments/exp10_fiqa_hnswlib/analyze_results.py

echo "[step] compress raw trace artifacts"
"$PY" experiments/exp10_fiqa_hnswlib/finalize_raw_artifacts.py

echo "[step] independent sample checks"
"$PY" experiments/exp10_fiqa_hnswlib/independent_check.py

echo "[step] report"
"$PY" experiments/exp10_fiqa_hnswlib/generate_report.py

echo "[step] full test suite"
PYTHONPATH="src;tests" "$PY" -m pytest -q --disable-warnings --capture=tee-sys

echo "[pipeline] EXP-10B.1 COMPLETE"
