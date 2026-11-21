"""Recall and cost metrics.

Recall@10 is computed against the independently computed filtered exact
Top-K. When the authorized set has fewer than K records, the denominator is
the true ground-truth size (never padded with fabricated records), and the
case is flagged explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable

from .ground_truth import GroundTruth
from .search_common import SearchOutcome


def recall_at_k(outcome: SearchOutcome, gt_indices: Iterable[int]) -> float:
    gt = set(int(v) for v in gt_indices)
    if not gt:
        return 0.0
    returned = set(int(v) for v in outcome.result_ids if v is not None)
    return len(gt & returned) / len(gt)


def insufficient_ground_truth(gt: GroundTruth, query_id: int) -> bool:
    return gt.insufficient(query_id)
