# Slice 170 — Model residency manager

## Skald (what already existed)
- `LocalRuntime.load()`/`unload()` were per-runtime calls with no
  ownership tracking; nothing prevented two users from unloading a
  model the other still needed.

## Rúnhild (design)
`hugrgate/runtimes/residency.py`: `ResidencyManager`, a ref-counted
residency table. `acquire(runtime, model)` loads when the resident
model differs (unloading the old one first), bumps the refcount, and
returns a `ResidencyLease` context manager; `release` drops the
refcount but the model *stays loaded* — a warm cache, not an
unload-on-zero (corrected during slice 171: unload-on-zero would
leave nothing for the eviction policy to evict); `evict`
force-unloads regardless of refcount (driven by the slice-171
eviction policy); `touch` refreshes last-use for LRU. Stale leases
(a different model took over) are no-ops. One `RLock`; runtime
objects remembered per-manager so release/evict can unload without
callers holding the runtime.

## Eldra (what was built)
- `hugrgate/runtimes/residency.py` (new): `ResidencyManager`,
  `ResidencyLease`, `ResidencyEntry` (with `to_dict`).
- `tests/test_localrt_170_residency.py` (new, 10 tests, incl. an
  8-thread acquire/release race).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_170_residency.py -q` → 10 passed.
`ruff` clean, `mypy` clean.

## Védis (integration)
- Pure addition; runtimes untouched. Slice 171's eviction policy
  consumes `evict`/`snapshot`/`touch`.

## Scribe
Commit `feat(gjallarbu-170): model residency manager` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Concurrent `acquire` across *processes* (the lock is per-process;
  multi-process serving needs an external lock).
