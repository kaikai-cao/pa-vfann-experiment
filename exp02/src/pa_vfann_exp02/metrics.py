"""Recall@K and query-failure accounting for EXP-02."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def recall_at_k(gt_indices: Sequence[int], result_ids: Sequence[int | None]) -> float:
    """Recall@K; NaN when ground truth is empty (never divide by zero)."""
    gt = set(int(v) for v in gt_indices if v is not None)
    if not gt:
        return float("nan")
    got = set(int(v) for v in result_ids if v is not None)
    return len(gt & got) / len(gt)
