# H1-RM.3A.7 — Private ACL × C0/C1/C2: observation-boundary smoke

## Purpose

Connect the 3A.5 `SecretAclFilter` to the original RM2 C0/C1/C2 search
mechanisms **without** running an attack evaluation. The goal is to fix the
observation boundary before any data is produced for a classifier.

Explicitly out of scope: A0/A1 pairs, multiple ACL instances, classifier
training, BA/AUC/attack advantage, page-level mapping or physical trace
simulation, 3B, and any change to the overall `CONDITIONAL` verdict.

## Phase A — event data-flow audit (fixed before producing data)

Sources read: `experiments/h1_rm2_native_stop/main.cpp`, the RM2-instrumented
`hnswalg.h`, `rm2_sink.h` / the `RM2_EV` macro, `hnsw_acl_filter.h`, and
`acl_bitmap.h`.

| Data | Needed internally? | Directly usable in attacker view? |
| --- | --- | --- |
| Node visit / traversal event (`distance_eval`, `candidate_pop`) | yes | judgement per threat model; kept only as a logical proxy |
| Search stop position (`stop_check`, `search_stop`) | yes | judgement per deployment observability; kept WITHOUT label or flag |
| Whether a filter callback was invoked (`filter_check` existence) | yes | **no** — not assumed observable |
| `authorized(label)` true/false (`filter_check.extra`) | yes | **never — absolute prohibition** |
| ACL bitmap / seed / target-member state | yes | **never — absolute prohibition** |
| Query / request boundary | yes | per deployment assumption; `query_id` is public in this smoke |

Critical finding beyond the `filter_check.extra` issue:

> In `searchBaseLayerST`, `result_add` / `result_remove` are emitted only
> inside the branch that passes `isIdAllowed`. Their label sets therefore
> **are the authorized set** even if `filter_check` is removed. Deleting the
> `extra` field alone does NOT close the leak. `n_filter_ok`, `auth_hits`
> and `khit_event_index` are equally internal-only.

RM2 currently records HNSW **logical control-flow events**, not physical page
accesses. Defining an attacker-view subset of these events does NOT make them
equivalent to what an OS/TEE page observer can see. The proxy below is only a
`logical_observation_proxy`; `is_physical_page_trace` is explicitly `false`.

## Two-layer output contract

For each group `C0`, `C1`, `C2` the program writes two separate files.

### `internal_diagnostics_C*.jsonl` — trusted internal data

- Begins with `record_type=internal_trusted_notice`,
  `attacker_observable=false`, `do_not_use_for_attack_evaluation=true`.
- Contains **all** events, including `filter_check` (with `extra` =
  authorization bit), `result_add`, `result_remove`, `internal_id`,
  `external_id`, `dist_bits`.
- Per-query `group_summary` includes `auth_hits`, `khit_event_index`,
  `n_filter_check`, `n_filter_ok`, `result_all_authorized`.
- Used solely to verify program behaviour. Never fed to an attack view.

### `observer_proxy_C*.jsonl` — untrusted logical observation proxy

- Begins with `record_type=observer_proxy_notice`,
  `trust=untrusted_observer_view`,
  `trace_kind=logical_observation_proxy`, `is_physical_page_trace=false`.
- **Drops** `filter_check`, `result_add`, `result_remove` entirely.
- **Drops** `extra`, `internal_id`, `auth_hits`, `khit_event_index`,
  `n_filter_ok` and every other authorization-derived field.
- Keeps `query_id`, `group`, `event_index`, `event_type`. Only
  `distance_eval` additionally keeps `external_id`, `level`, `dist_bits`
  (node-touch/distance observations allowed by the logical threat model).
- `stop_check` / `search_stop` keep only position and type — no label, no
  stop flag, no hint about which callback authorised.
- `event_index` is a **dense, observer-only counter** (see R1 below). It is
  NOT the internal event index.

## R1 — dense observer event index (side-channel fix)

In the original 3A.7 output the observer proxy reused the internal
`event_index` verbatim. Because the three internal-only event types
(`filter_check`, `result_add`, `result_remove`) are removed from the observer,
the surviving internal indices contained **gaps**: the gap count and positions
encoded how many internal events had been dropped and where — a side channel
through the index field alone, independent of any event field.

R1 changes ONLY the observer proxy writer:

- `event_index` in `observer_proxy_C*.jsonl` is now a **dense counter that is
  regenerated after filtering**: `0, 1, 2, ...` over exactly the events that
  are actually written, in their original relative order.
- The counter is reset at the start of every (query, C-group).
- It no longer corresponds to the internal event index. An observer cannot
  infer the count or position of removed internal events from it.
- The internal diagnostics layer keeps its **original, unmodified**
  `event_index` (consecutive over all internal events, gaps included); nothing
  about the trusted layer changed.

This is a **narrow fix to the index side channel only**. It does NOT mean the
observer trace is free of ACL-related information: surviving event types,
their counts, positions, labels and distances may still correlate with the
secret ACL under a threat model. No classifier / BA / AUC was run and no claim
about residual leakage is made here. C0/C1/C2 search logic, the ACL fixture,
the stop conditions and all internal diagnostics are unchanged.

## C0 / C1 / C2 definitions (mirroring RM2, independently implemented)

- **C0**: `searchKnn(q, K, &filter)` — standard search.
- **C1**: `searchStopConditionClosest(q, EfReplayStopCondition, &filter)`.
  The stop condition replays the real `ef` rule with a mirrored result set
  `R_` (not a scalar counter).
- **C2**: C1 plus `KHitStopCondition`, whose extra stop test is
  `auth_hits >= K`; `auth_hits` counts **only** authorized filter passes and
  is reset to zero at the start of every query/group.

All three groups share one ACL instance, one index, one query batch, and the
same `K = 5`, `ef = 64`. The callback is a locally derived class whose
decision is delegated to `SecretAclFilter::operator()`; no public-hash
`authorized()` from RM2 is used.

**Upstream v0.9.0 return-value quirk (handled in this harness only):** the
frozen `searchKnn()` converts internal `tableint` ids to external labels
before returning, but `searchStopConditionClosest()` copies internal ids
straight into its returned `pair`. The harness therefore calls the existing
public `index.getExternalLabel()` for C1/C2 results before any ACL check.
No frozen header was edited to work around this.

## Synthetic setup

`n = 200`, `dim = 8`, inner-product space, `M = 16`, `ef_construction = 200`,
`ef_search = 64`, `seed = 2026`, `NQ = 6`, labels `100000 + 17*i`.
The Python test writes a fixed vector with `bit[i] = 1` iff `i % 10 == 0`
(20 authorized members) using the existing 3A.4 `encode_acl_bitmap()`. This
is a fixed non-real test vector; no A0/A1 pairing and no target selection.

## Run

```bash
python -m pytest tests/test_h1_rm3a7_secret_acl_c0c1c2_smoke.py -v
```

or

```bash
python -c "import sys; sys.path.insert(0,'experiments/h1_rm_3a4_secret_acl'); \
import acl_bitmap as ab; open('/path/fixture.bin','wb').write( \
ab.encode_acl_bitmap([1 if i%10==0 else 0 for i in range(200)]))"
bash experiments/h1_rm_3a7_secret_acl_c0c1c2_smoke/build_and_run.sh \
    /path/fixture.bin /path/outdir
```

## Acceptance checks

The pytest suite verifies: all returned labels satisfy the ACL; C2 K-hit is
actually exercised; every `filter_check.extra` equals the bitmap bit for
that label; per-query `auth_hits` equals the number of authorized callbacks;
internal and observer layers are strictly separated; the observer proxy
contains no authorization boolean and no authorized-only event type; and
outputs are byte-repeatable. Exit code is non-zero if any invariant fails.
