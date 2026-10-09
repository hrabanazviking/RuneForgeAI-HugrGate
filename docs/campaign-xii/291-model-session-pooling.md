# Slice 291 — Model-session pooling

**Status:** complete. Commit: `feat(gjallarbu-291)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

The local-model fabric (`LocalRuntime.load/unload`, slice 151) had no
session reuse: every consumer paid full model-load cost per use. The
residency layer (slices 170–171) tracks *which models are resident*
under VRAM pressure, but nothing pooled *loaded sessions* above it.

## What was built

- `hugrgate/runtimes/session_pool.py` — new module:
  - `ModelSessionPool`: one `ResourcePool` (slice 290, reused) per
    `ModelRef`; the per-model factory builds the runtime via the
    caller's `runtime_factory` and calls `load(model)` exactly once
    per session. Later acquires for the same model reuse the warm
    session — handles are `PooledHandle`, `handle.resource` is the
    loaded `LocalRuntime`.
  - Cross-model LRU eviction at `max_models` (evicted pools shut down;
    sessions closed).
  - Checkout health via `runtime.health()["status"] == "ok"`; sick
    sessions discarded and rebuilt; `handle.discard()` for mid-use
    failures.
  - `drop_model(model)`: the seam for `runtimes.eviction` — evicting a
    resident model also drops its pooled sessions.
  - Exhaustion/config errors raise the slice-290 `PoolError`
    (Anti-Checkbox: reused, not duplicated).
  - Contract documented: pooled runtimes must release model resources
    in `close()`.

## Tests

`tests/test_perf_291_session_pool.py` — 14 tests with a counting
`FakeSessionRuntime`: warm reuse (load once), per-model isolation,
per-model cap + exhaustion, LRU eviction order (touch-based), drop
seam (incl. rebuild), sick-on-checkout discard, mid-use discard, load
failure → `PoolError`, bad factory/model/config rejection,
post-shutdown rejection, stats shape, shutdown closes all. All green;
ruff clean; import-cycle, dependency-layering, and runtime-interface
tests green.
