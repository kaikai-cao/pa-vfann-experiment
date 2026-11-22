# PA-VFANN-10 / EXP-02 — Remove the Global Distance Oracle

**Branch:** `exp02-no-distance-oracle` · **Baseline:** `0145cca` (EXP-01, unchanged)
**Research question:** without global query-to-database distance precomputation or a global nearest-point entry, does fixed-trace filtered ANN still give a meaningful recall / computation / communication trade-off under different authorization selectivities?

EXP-01 code, CSVs, figures and report are untouched. Everything new lives under `exp02/`.

## 1. What was actually fixed in the experimental model

| EXP-01 defect | EXP-02 replacement |
|---|---|
| `squared_l2_to_all()` precomputed query → all 10,000 vectors | no such table in any search path; `DistanceMeter.get(node)` computes one vector pair on first use |
| `np.argmin(row)` used global nearest node as entry | fixed public `entry_node_id = 8817` (seed-derived, pinned literal in config) |
| search could read any node's exact query distance for free | only discovered nodes have cached distances; each counts as one `distance_evaluations` |
| full-database distance computation was free | it exists only in `ground_truth.py`, isolated from every ANN cost column |

`entry_node_id` is generated once by
`int(np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026, 0x4558503032]))).integers(0, 10000))`
and verified against the config literal at every run. It depends on neither query, policy, nor authorization labels. **A fixed entry is not a fixed trace**: all three algorithms still use query-driven best-first priority; only E3 forbids policy-dependent decisions.

## 2. Reuse audit for EXP-01 modules

`src/pa_vfann_exp02/exp01_bridge.py` imports only offline generators; EXP-01 search modules and its precomputed distance table are never imported into the search path.

| Reused module | Usage | Audit result |
|---|---|---|
| `dataset.build_dataset` | vectors / queries from seed 2026 | no query distances; identical data to EXP-01 |
| `graph.build_graph` | exact-kNN graph (out-degree 16 + reverse union) | dataset-to-dataset distances only; public offline structure, not a query oracle; NOT HNSW |
| `policies.build_policy` | Random / Clustered authorization labels | dataset-to-centre affinities for label generation only; labels identical to EXP-01 |
| `dataset.squared_l2_to_all` | imported **only** by `ground_truth.py` | full exact table for filtered GT; its cost is never added to ANN counters |
| `leakage.{set_leakage, normalized_edit_distance}` | pure trace metrics | no distance information |

Tests assert the search source contains no `squared_l2_to_all`, `np.argmin` or matrix multiply against all vectors.

## 3. Cost semantics (four independent counters)

- **discovered** — node first enters the candidate queue; its distance is computed here exactly once.
- **visited** — node is popped from the queue and processed.
- **expanded** — node's adjacency list is enumerated; **one expansion consumes one budget unit**.
- **neighbor check** — one adjacency edge inspected (duplicates counted).

After the last permitted expansion, one final node may be popped and recorded as visited but is never expanded; this is identical for all algorithms. Counters come from the state machine's snapshots (and are verified against direct lower-budget runs), never from another metric. Ground-truth work is excluded.

## 4. The three algorithms

**E1 — Adaptive Post-filter.** Fixed entry; lazy-distance best-first queue; distance-only priority. The server checks authorization when a node is discovered; authorized discovered nodes form the result candidate pool; unauthorized nodes are still expanded as ordinary graph nodes. Once legal candidates ≥ K and at least `min_expansions_before_stop = 20` expansions have occurred, search stops early (`termination_reason = early_stop`). Otherwise it runs to the budget. Results: nearest K authorized discovered nodes.

**E2 — Predicate-aware Search (custom controlled bridge, not ACORN/RACORN).** Fixed entry; lazy-distance best-first queue ordered by squared L2 distance. Authorized nodes enter the result pool and reset the consecutive-bridge counter to 0. Unauthorized nodes never enter results but may bridge: an unauthorized neighbor is discovered with hop 1 after an authorized parent, or with hop `parent_hop + 1` after an unauthorized parent, provided that hop ≤ `r` (`r ∈ {1,2,4}`). Beyond `r`, an unauthorized neighbor is checked (counted in `neighbor_checks`) but not discovered. Duplicate discoveries are ignored; first discovery fixes the hop. E2 has no policy-driven early stop and runs to the expansion budget or queue exhaustion.

**E3 — Fixed-trace Private Filtering.** Fixed entry; lazy-distance best-first queue; fixed expansion budget; **no authorization argument, bit, label or legal-count read anywhere in the search**. No early stopping. After the trace is complete, the whole discovered candidate set is handed to a *simulated* client-side secret filter, which selects the nearest K authorized candidates; placeholders are emitted when fewer than K exist. Invariant tested directly:

```
same query + same graph + same public entry + same expansion budget + different policy
  => identical E3 discovery / visit / expansion sequences
```

This is a plan-independence property, **not** cryptographic privacy and **not** output hiding: returned IDs and candidate counts still depend on the policy.

## 5. Candidate transfer model

The server sends the discovered candidate set (not just the visited prefix) after the search. Fixed little-endian serialization: ID = `<I` (4 B); distance metadata = `<f` (4 B); vector = `dimension × <f` (512 B at d=128). Reported separately: ID-only (4 B/candidate), ID+metadata (8 B/candidate, the default `candidate_transfer_bytes`), ID+full vector (516 B/candidate). The server never sends an authorization bit.

## 6. Ground truth and recall

`ground_truth.py` brute-forces exact L2 over **all** authorized records for every query, independent of any ANN search and outside all cost counters. `effective_k = min(K, authorized count)`; when the authorized set is empty, Recall is reported as N/A (never fabricated). Recall is computed per query and then averaged; failed queries are kept in the raw CSV.

## 7. Reproduce

Python 3.11+ (validated on CPython 3.14); dependencies: numpy, scipy, pandas, matplotlib, pyyaml, pytest.

```bash
cd D:/Research/pa-vfann-experiment
PYTHONPATH="src;exp02/src" python -m pytest -q exp02/tests
python exp02/scripts/run_all.py
# smoke run:
python exp02/scripts/run_all.py --config exp02/config/experiment_smoke.yaml
```

Parameters: 10,000 vectors / 128 dims / K=10 / graph out-degree 16 / 200 queries / seed 2026 / selectivities 1, 5, 10, 30% / Random and Clustered policies / expansion budgets 20, 50, 100, 200, 500, 1000 / `r ∈ {1,2,4}` / leakage budgets 100 and 500.

Outputs: `exp02/results/raw/experiment_results.csv`, four summary tables, five figures and `exp02/REPORT.md`.

## 8. Boundaries

No MPC, ORAM, SNARK, Halo2, HNSW or real ANN index is implemented. The controlled exact-kNN graph is a simulator, not HNSW. `secret_filter` is a simulated client interface, not a cryptographic protocol. No EXP-01 results were deleted and no EXP-01 file was modified.
