# H1-RM.3A.8 — A0/A1 Paired ACL Feasibility

Feasibility only. This stage confirms that the existing 3A.7 harness can
construct and run a strictly paired counterfactual ACL pair and produce
comparable observer traces. It does **not** evaluate an attack.

Explicitly out of scope: classifier training, BA/AUC/attack advantage,
page-level or physical trace mapping, multiple independent ACL instances,
any change to the search algorithm, and any change to the overall
`CONDITIONAL` verdict.

## Pre-registered public constants (frozen for this stage)

| Constant | Value |
| --- | --- |
| `N_MEMBERS` | 200 |
| target selection seed | `H1-RM.3A8-TARGET-SEED-20261126` (public, pre-registered) |
| target count | 1 (`u`) |
| ACL prior | one base ACL from system CSPRNG, `p = 1/10` natural prior |
| label mapping | `100000 + 17*i` (matches the frozen bitmap loader) |
| index / queries | the 3A.7 fixed synthetic setup (`dim=8`, `M=16`, `ef_c=200`, `ef=64`, `K=5`, `NQ=6`, `seed=2026`), UNCHANGED |

## Counterfactual construction (order matters)

1. `u = select_targets(200, 1, PUBLIC_SEED)` — called BEFORE any ACL exists.
   It receives only public quantities; it cannot see an ACL, bit, distance,
   K-hit position, observer trace or any search result.
2. `base = sample_acl_bitmap(200)` — one private ACL from `secrets.randbelow`.
3. `(A0, A1) = derive_target_pair(base, u)` — a fresh pair with
   `A0[u]=0`, `A1[u]=1`, and `A0[i]=A1[i]` for every `i != u`.
4. Assert `diff_indices(A0, A1) == [u]`; encode both with the existing 3A.4
   encoder and write the blobs to a caller-supplied PRIVATE directory.

Complement-style fixtures (the `BITS_A` / `BITS_B` pair used in earlier tests)
are deliberately NOT used: they flip many members and are not a single-bit
counterfactual.

**A0/A1 are researcher-side counterfactuals.** A real attacker observes only
the one ACL state that actually exists; nobody observes both worlds.

## Search integration

The UNMODIFIED 3A.7 harness (`experiments/h1_rm_3a7_secret_acl_c0c1c2_smoke/`)
is compiled as-is and run twice — once per ACL — into separate output
directories. Same index, same query vectors, same `K=5`, `ef=64`, same six
queries, same C0/C1/C2 mechanisms, same R1 observer-proxy schema. The only
difference between the two runs is the single target bit in the ACL.

`internal_diagnostics_C*.jsonl` is researcher-side verification material only;
it is never mixed into the observer view and is never an attacker input.

## Run

```bash
python -m pytest tests/test_h1_rm3a8_acl_pair_feasibility.py -v

# or produce a one-off report under a PRIVATE directory (never inside the repo):
python experiments/h1_rm_3a8_acl_pair_feasibility/pair_driver.py /private/path/work
```

All generated ACL blobs, diagnostics and traces live under a caller-supplied
private directory (pytest uses `tmp_path`). The driver prints only structural
summaries — no bitmap contents, no private paths, no authorized counts.

## The three independent result layers

The driver's report keeps these layers separate on purpose. A result in one
layer must NOT be read as a result in another.

### Layer 1 — Pairing integrity (structural, sound)
Are A0/A1 really one bit apart, with A0[u]=0 and A1[u]=1 and all other bits
identical? Are the encodings/decodings consistent and loadable by the C++
loader? This is a hard invariant; the run stops if it fails.

### Layer 2 — Observation feasibility (structural, sound)
Did the target `u` actually enter the search and the observer view? Three
conditions are checked INDEPENDENTLY and never conflated:

- `internal_distance_eval`: target was visited during search (internal only).
- `internal_filter_check`: target triggered an ACL callback (internal only).
- `observer_visible`: target's label appears in the observer proxy.

A target being visited does not imply it triggered a callback; triggering a
callback does not imply it is observer-visible. If the target is absent from a
group, the report records that fact; the target is NEVER re-picked to force a
desired outcome.

### Layer 3 — Trace sensitivity (evidence only, NOT a leakage proof)
For C0, C1 and C2, compare the A0 vs A1 observer traces: field schema, event
order, event count and content. A one-bit change coinciding with a trace
change is **sensitivity evidence**, not statistical evidence that an attacker
can infer the authorization state. Conversely, identical traces do NOT prove
the state is unlearnable. No classifier, BA, AUC or attack advantage is
computed here.

Observed under the frozen seed (single fixed fixture, 6 queries aggregated):

| Group | A0 observer events | A1 observer events | content equal? |
| --- | --- | --- | --- |
| C0 | 4926 | 4926 | yes |
| C1 | 4926 | 4926 | yes |
| C2 | 902 | 850 | no |

The C0/C1 traces are identical; C2 differs, with the first divergence at a
`candidate_pop` vs `search_stop` event — consistent with the K-hit stop early
termination, but this is an observation, not a measured security claim.

## Acceptance / stop conditions honoured

- Single-bit pair invariant enforced as a hard stop.
- Target selection depends only on public seed, before ACL generation.
- No 3A.4/3A.5/3A.6/3A.7 source, frozen HNSW header or R1 proxy was modified.
- Observer output contains no ACL bit, authorization counter or internal
  diagnostic field (asserted by tests).
- Both runs use the same index and query configuration.
- Private ACL fixtures, internal diagnostics and the full manifest are not
  committed.
