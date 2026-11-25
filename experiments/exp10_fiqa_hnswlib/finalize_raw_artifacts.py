#!/usr/bin/env python3
"""Compress raw EXP-10B.1 trace artifacts and record reproducible hashes."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "results" / "raw"
NAMES = (
    "exp10_fiqa_trace_events.jsonl",
    "exp10_fiqa_first_touch.jsonl",
    "exp10_fiqa_hnsw_topk.jsonl",
    "exp10_fiqa_probe_summary.jsonl",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    manifest = {"experiment": "EXP-10B.1", "artifacts": {}}
    for name in NAMES:
        src = RAW_DIR / name
        dst = RAW_DIR / (name + ".gz")
        if not src.exists():
            raise RuntimeError(f"missing raw artifact: {src}")
        with src.open("rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout)
        manifest["artifacts"][name] = {
            "compressed_path": str(dst.relative_to(ROOT)).replace("\\", "/"),
            "raw_size_bytes": src.stat().st_size,
            "compressed_size_bytes": dst.stat().st_size,
            "raw_sha256": sha256_file(src),
            "compressed_sha256": sha256_file(dst),
        }
        print(f"[compress] {name}: {src.stat().st_size} -> {dst.stat().st_size} bytes", flush=True)
    path = RAW_DIR / "exp10_fiqa_trace_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[manifest] {path.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
