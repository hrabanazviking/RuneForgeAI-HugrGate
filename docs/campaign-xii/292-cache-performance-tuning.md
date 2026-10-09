# Slice 292 — Cache performance tuning

**Status:** complete. Commit: `feat(gjallarbu-292)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

`DecisionCache` hot-path profile (12-key state, this VM):

- `get` hit ≈ 38µs = `cache_key` (~20µs) + `copy.deepcopy` (~17µs)
- `cache_key` = `json.dumps(..., sort_keys=True)` + sha256; the
  `sort_keys` re-sorted every nested mapping in C — including the
  spec/policy subtrees, which are *already* built in canonical order
  and gain nothing from sorting.
- A hand-rolled Python canonical byte-encoder was tried and **rejected**:
  45µs vs 19µs — Python per-value dispatch loses to the C encoder.
- blake2b was tried and **rejected**: slower than sha256 at these
  payload sizes (8.05µs vs 4.90µs) on this OpenSSL build.

## What was built (`hugrgate/cache.py`)

1. **`_canonicalize`**: recursive Python-side key sort of *only the
   state subtree* (the one nondeterministic part); `json.dumps` now
   runs without `sort_keys`. Semantics preserved: insertion-order
   variants (nested included) hash equal; tuple/list parity kept;
   mixed-type keys still raise `TypeError`; `default=str` fallback
   unchanged.
2. **`_isolated_copy`**: replaces `copy.deepcopy` on `get`/`put`.
   Exact-`DecisionResult` fast path copies only the known mutable
   fields (`distribution` is `dict[str, float]` → flat `dict()`;
   `metadata` → `deepcopy` for arbitrary nesting). Subclass instances
   keep the old `deepcopy` behavior.

## Measurements (real, seeded, reproducible)

- Harness: `benchmarks/cache_tuning.py` (seed 292; 1000 shuffled states,
  4000 iters/op, 20000-op mixed workload).
- Artifacts: `benchmarks/cache_tuning_baseline.json` (pre-tuning),
  `benchmarks/cache_tuning_tuned.json` (post-tuning).
- **Caveat (honest):** this VM shows ±50% run-to-run noise on
  sequential full-workload runs, so the artifacts alone are not the
  verdict. The decisive evidence is same-process interleaved A/B
  (5 rounds, both variants under identical VM conditions):
  - `cache_key`: 28.92µs → 23.97µs median (**−17%**, tighter variance)
  - result copy: 20.19µs → 8.90µs min (**−56%**, 2.3× faster)
  - subclass copy path verified equal to old `deepcopy` cost/behavior.

## Tests

`tests/test_perf_292_cache_tuning.py` — 11 tests: key determinism,
top-level and nested order-insensitivity, sensitivity to
state/spec/policy changes, tuple/list parity, `str()` fallback,
`TypeError` parity, put/get isolation (incl. nested metadata),
copy type/value preservation, subclass deepcopy fallback. All green;
44 cache-related tests across the suite green; ruff clean.
