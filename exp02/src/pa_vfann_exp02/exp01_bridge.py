"""Audit and reuse of EXP-01 offline generators.

Audited imports (all are offline / pre-search and contain no query-distance
oracle inside any search routine):

  * dataset.build_dataset   -- i.i.d. vectors and queries from a fixed seed;
  * graph.build_graph       -- exact-kNN graph of the *dataset*, built once from
                               dataset-to-dataset distances (public offline
                               structure, not query-to-database distances);
  * policies.build_policy   -- authorization labels from seed + dataset-to-
                               centre affinities (offline label generation);
  * dataset.squared_l2_to_all -- FULL query-to-database distance table. Used
                               ONLY by exp02.ground_truth, never by search.
  * leakage helpers         -- pure set/edit-distance metrics.

Nothing in exp01_bridge imports EXP-01 search modules or distance tables into
the search path. The EXP-01 source files are not modified.
"""

from __future__ import annotations

import sys

from .config import exp01_src

_SRC = str(exp01_src())
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pa_vfann.dataset import Dataset, build_dataset, squared_l2_to_all  # noqa: E402
from pa_vfann.graph import Graph, build_graph  # noqa: E402
from pa_vfann.leakage import normalized_edit_distance, set_leakage  # noqa: E402
from pa_vfann.policies import Policy, build_policy  # noqa: E402

__all__ = [
    "Dataset", "Graph", "Policy", "build_dataset", "build_graph", "build_policy",
    "squared_l2_to_all", "set_leakage", "normalized_edit_distance",
]
