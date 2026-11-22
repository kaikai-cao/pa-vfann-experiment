"""EXP-02 configuration loading and repository path helpers."""

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


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path is not None else default_config_path()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {path}")
    required = ("data", "query", "graph", "search", "policies", "serialization")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"config missing sections: {missing}")
    return Config(raw=raw, path=path)


def exp02_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return exp02_root().parent


def exp01_src() -> Path:
    return repo_root() / "src"


def default_config_path() -> Path:
    return exp02_root() / "config" / "experiment.yaml"
