"""Audit configuration loader (paths resolved relative to the repo root)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
AUDIT_ROOT = ROOT / "exp02a"


class AuditConfig:
    def __init__(self, raw: dict, path: Path | None = None):
        self.raw = raw
        self.path = path or AUDIT_ROOT / "config" / "audit.yaml"

    def __getitem__(self, key: str):
        return self.raw[key]

    def resolve(self, key: str) -> Path:
        """Resolve a baseline path as repo-root-relative."""
        p = Path(self.raw["baseline"][key])
        return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()


def load_config(path: str | Path | None = None) -> AuditConfig:
    p = Path(path) if path else AUDIT_ROOT / "config" / "audit.yaml"
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return AuditConfig(yaml.safe_load(p.read_text(encoding="utf-8")), p)
