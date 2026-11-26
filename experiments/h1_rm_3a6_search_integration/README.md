# H1-RM.3A.6 — Actual HNSW Search Integration

## Scope

This is a **single, minimal search-correctness experiment**. It verifies that
`SecretAclFilter`, passed as the `isIdAllowed` argument of a real
`hnswlib::HierarchicalNSW<float>::searchKnn()` call, actually constrains the
returned labels.

It is **not** an attack experiment. It does not run C0/C1/C2, does not emit
page/block traces, does not generate A0/A1 pairs, does not train a classifier
and does not compute any attack metric. Overall research verdict remains
`CONDITIONAL`.

## Files

- `main.cpp` — builds one synthetic index, runs unfiltered and filtered
  `searchKnn()` against the same index/query/k/ef, checks invariants.
- `build_and_run.sh` — reproducible compile + run helper.
- `../tests/test_h1_rm3a6_search_integration.py` — fixture generation via the
  existing `encode_acl_bitmap()`, dual-header compilation, assertions,
  repeatability check.

No historical file is modified: `hnswalg.h`, `hnswlib.h`, `StorageAccess`,
`main.cpp` of earlier experiments and the 3A.4/3A.5 sources are untouched.

## Synthetic fixture (fixed, non-real)

`n = 64`, `N > 0` as required by the 3A.5 contract. The Python test writes
`bitmap = [1] * 16 + [0] * 48` using `encode_acl_bitmap()` from 3A.4. This is a
**fixed test vector**, not an experiment ACL instance. The blob contains no
seed, authorized count, target state, pair marker or instance identity.

External labels follow the frozen mapping `100000 + 17 * i`, identical to
`AclBitmap::lookup_label()` and `label_to_index()`.

## Synthetic geometry

Points are 2-dimensional. The C++ harness derives each point's position from
the ACL bit through the **public loader** (`lookup_index`):

- authorized bit = 1 → far from the query (`x = 100 + 0.01*i`);
- authorized bit = 0 → near the query (`x = 1 + 0.01*i`);
- query is the origin; L2 distance.

Consequences that make the test discriminating:

1. Unfiltered Top-K contains unauthorized labels (the nearest points).
2. A *post-hoc* filter over unfiltered results would return an **empty** set.
3. Therefore a non-empty filtered result whose labels are all authorized and
   absent from the unfiltered Top-K can only arise if the callback was
   consulted **during** `searchKnn()` traversal.

An auxiliary derived filter (`CountingSecretAclFilter`, defined locally in
`main.cpp`, no historical edits) records callback invocations. The primary
filtered search still passes a plain `SecretAclFilter`, exactly as specified.

## Parameters (identical for both searches)

| parameter | value |
| --- | --- |
| index | one `HierarchicalNSW<float>` instance |
| metric | `L2Space(2)` |
| `M` / `ef_construction` | 16 / 200 |
| `ef` (search) | 64 |
| `k` | 5 |
| random seed | 100 |
| query | `(0, 0)` |

ANN recall is **not** an evaluation metric here, and filtered results are not
required to equal exact Top-K.

## Header sets

Compiled and executed against both frozen header directories:

- `third_party/hnswlib-v0.9.0/hnswlib` (pristine)
- `third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib` (RM2 instrumented;
  its `RM2_EV` trace macro is compile-time gated and off in this experiment,
  so no page/trace events are emitted)

## Output contract

```
LOAD OK
UNFILTERED <label> ...
FILTERED <label> ...
META n=<n> k=<k> ef=<ef> callback_calls=<count>
CHECK unfiltered_has_unauthorized=1
CHECK filtered_nonempty=1
CHECK filtered_all_authorized=1
CHECK filtered_outside_unfiltered_topk=1
CHECK callback_invocations_positive=1
CHECK counting_run_all_authorized=1
RESULT PASS
```

Exit code `0` only when every `CHECK` is `1` and `RESULT PASS`; otherwise
non-zero. Printed labels are synthetic test labels from a fixed non-real
fixture; the program never prints bitmap contents, an authorized member list,
file paths or seeds.

## Run

Via pytest (preferred; writes the fixture into pytest's temporary directory):

```bash
python -m pytest tests/test_h1_rm3a6_search_integration.py -v
```

Or manually:

```bash
python -c "import sys; sys.path.insert(0,'experiments/h1_rm_3a4_secret_acl'); \
import acl_bitmap; open('/tmp/acl.bin','wb').write(acl_bitmap.encode_acl_bitmap([1]*16+[0]*48))"
bash experiments/h1_rm_3a6_search_integration/build_and_run.sh \
    third_party/hnswlib-v0.9.0/hnswlib /tmp/acl.bin
```

## Unverified by this stage

Whether C1/C2 trajectories leak target membership; whether the K-hit stopping
behaviour induces an incremental leak; any real ACL instance, A0/A1 pair,
page-level proxy trace or attack accuracy. None of these are claimed here.
