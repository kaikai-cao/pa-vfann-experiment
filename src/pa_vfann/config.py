"""Configuration loading for PA-VFANN-09 / EXP-01.

The repository uses a single YAML file with all frozen experiment parameters.
Every stochastic component derives its RNG from the one master seed in the
config, so a run is reproducible from ``config/experiment.yaml`` alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    path: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {path}")
    required = ("data", "query", "graph", "search", "policies")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"config missing sections: {missing}")
    return Config(raw=raw, path=path)


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "experiment.yaml"
