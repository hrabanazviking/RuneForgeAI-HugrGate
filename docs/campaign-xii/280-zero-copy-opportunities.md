# Slice 280 — Zero-copy opportunities

**Status:** complete. Commit: `feat(gjallarbu-280)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

`DecisionCache` (slice 38) pays `copy.deepcopy` on every `put` **and**
every cache hit — the safety rail against caller mutation. For results
that are never mutated after caching, that copy is pure tax. This slice
removes it without removing the rail.

## What was built

- `hugrgate/zerocopy.py` — new module:
  - `freeze(result)` → `FrozenDecisionResult`: one deepcopy at freeze
    time, then fully immutable (attribute writes raise `ZeroCopyError`;
    `distribution`/`metadata` exposed as read-only mapping proxies).
    `thaw()` recovers a mutable `DecisionResult` when needed.
  - `ZeroCopyCache`: TTL/LRU cache mirroring `DecisionCache`'s contract
    (privacy gate, backend invalidation, hit/miss stats) that serves
    the **identical** frozen object per hit — zero copies per hit, zero
    per put. `put` of an unfrozen result raises unless
    `freeze_on_put=True`. `stats()` reports `copies_per_hit: 0`.
  - `SharedPayload`: immutable pre-encoded bytes (encode once, serve by
    reference) for cluster transport payloads.
  - `copy_cost_estimate(result)`: measures the deepcopy tax in
    µs/copy so the win is a number, not a claim.
- `hugrgate/errors.py` — new `ZeroCopyError` (`code="zerocopy_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`. (First
  draft subclassed `ProfilingError` and reused its code — caught before
  commit: it would have clobbered `HugrGateError._registry`'s
  `from_dict` mapping. Separate code per the taxonomy law.)

`DecisionCache` itself is untouched: mutable results keep the deepcopy
rail. Zero-copy is opt-in via freezing.

## Tests

`tests/test_perf_280_zerocopy.py` — 19 tests: freeze fidelity/
idempotence/rejection, attribute + nested-mapping immutability,
freeze-copies-once isolation, thaw round-trip, equality, cache
identical-object hits, miss/expiry, unfrozen-put rejection,
freeze-on-put, LRU eviction, privacy gate, backend invalidation, bad
config, payload encode-once identity, cost measurement, and a
**measured** shared-serve vs deepcopy comparison (shared wins; the tax
is real, >1µs/copy on a 64-option distribution). All green; ruff
clean; import-cycle test green.
