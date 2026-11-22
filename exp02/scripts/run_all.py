"""One-command EXP-02 reproduction: tests -> selectivity -> leakage -> tables/figures."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(command: list[str]) -> None:
    print(f"\n>>> {' '.join(str(c) for c in command)}", flush=True)
    subprocess.run([str(c) for c in command], cwd=ROOT, check=True,
                   env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src") + ";" + str(ROOT.parent / "src") + ";" + str(ROOT / "experiments")})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--config", default=str(ROOT / "config" / "experiment.yaml"))
    args = parser.parse_args()
    if not args.skip_tests:
        run([PY, "-m", "pytest", "-q"])
    run([PY, ROOT / "experiments" / "run_selectivity.py", "--config", args.config])
    run([PY, ROOT / "experiments" / "run_leakage.py", "--config", args.config])
    run([PY, ROOT / "experiments" / "make_report.py", "--config", args.config])


if __name__ == "__main__":
    main()
