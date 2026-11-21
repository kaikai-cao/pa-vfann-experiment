"""One-command reproduction of PA-VFANN-09 / EXP-01.

Order: unit tests -> selectivity experiment -> correlation/leakage experiment
-> summary tables and figures. The raw CSV is reset at the start so repeated
runs never duplicate rows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pa_vfann.config import default_config_path, load_config  # noqa: E402


def run(command: list[str], env: dict | None = None) -> None:
    print(f"\n>>> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def main() -> None:
    args = sys.argv[1:]
    config_path = str(default_config_path())
    if "--config" in args:
        config_path = args[args.index("--config") + 1]
    config = load_config(config_path)
    python = sys.executable
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT))

    raw = ROOT / "results" / "raw" / "experiment_results.csv"
    if raw.exists():
        raw.unlink()

    if "--skip-tests" not in args:
        run([python, "-m", "pytest", "-q"], env)
    run([python, str(ROOT / "experiments" / "run_selectivity.py"), "--config", config_path], env)
    run([python, str(ROOT / "experiments" / "run_correlation.py"), "--config", config_path], env)
    run([python, str(ROOT / "experiments" / "make_report.py")], env)
    if "--skip-tests" not in args:
        run([python, "-m", "pytest", "-q"], env)
    print(f"\n[run_all] complete. raw={raw}", flush=True)


if __name__ == "__main__":
    main()
