#!/usr/bin/env python3
"""Build a manifest for H1-RM.3A.1 outputs (paths + sha256 + sizes)."""
import os
import sys
import json
import hashlib
import subprocess

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
OUT = os.path.join(ROOT, "results", "h1_rm_3a1")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    try:
        return subprocess.check_output(["git", "-C", ROOT] + list(args),
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def main():
    files = []
    for sub in ("baseline", "bridged", "comparison"):
        d = os.path.join(OUT, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                files.append({
                    "path": "results/h1_rm_3a1/%s/%s" % (sub, name),
                    "sha256": sha256(p),
                    "bytes": os.path.getsize(p),
                })
    manifest = {
        "experiment": "H1-RM.3A.1",
        "base_commit": git("rev-parse", "HEAD"),
        "parent_commit": git("rev-parse", "HEAD^"),
        "branch": git("branch", "--show-current"),
        "files": files,
    }
    p = os.path.join(OUT, "manifest.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("manifest files=%d" % len(files))


if __name__ == "__main__":
    main()
