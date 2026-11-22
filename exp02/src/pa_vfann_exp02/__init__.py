"""PA-VFANN-10 / EXP-02: no global distance oracle.

This package is independent from EXP-01's search code. It reuses only the
offline data/graph/policy generators from EXP-01 through an explicit bridge;
no query-distance table is used by any search strategy here.
"""

__all__ = ["config", "exp01_bridge", "lazy_search", "algorithms", "transfer", "ground_truth", "metrics"]
