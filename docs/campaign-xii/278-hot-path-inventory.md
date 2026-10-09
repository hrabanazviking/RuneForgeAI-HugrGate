# Slice 278 — Hot-path inventory

**Status:** complete. Commit: `feat(gjallarbu-278)` on `gjallarbu/campaign-xii`.

## What existed before

Slices 276–277 profiled single runs. Nothing aggregated across runs,
so there was no durable answer to "where does time consistently go?"
This slice builds the inventory the optimization slices (280–281, 292)
will work from.

## What was built

- `hugrgate/hotpaths.py` — new module:
  - `HotPathCollector(profiler, runs, label).collect(workload)` —
    profiles a workload N times and aggregates into a
    `HotPathInventory`.
  - `HotPathInventory.ranked()` — cumtime-descending ranking;
    `hot(threshold)` — flags functions owning ≥ threshold share of
    total profiled time (threshold validated in (0, 1]);
    `to_dict()` / `to_markdown()` renderers.
  - Aggregation sums cumtime/tottime/calls per function and counts
    `runs_seen`; `share` is documented as relative to summed cumtime
    across all profiled frames.
- Privacy note in the module docstring: inventories name backend
  internals, so the strict-privacy suppression rule from slice 276
  applies to persistence.

## Tests

`tests/test_perf_278_hotpaths.py` — 8 tests: slow-function ranking
(parent frame correctly outranks the child by cumtime), cross-run
aggregation sums, hot-threshold flagging + boundary validation,
constructor validation, serialization shape, zero-call percall guard,
end-to-end inventory over a real `gate.decide` workload (finds
`core:decide`). All green; ruff clean; import-cycle test green.

## Finding worth recording

Summing cumulative time double-counts nested frames — `share` is a
*relative cost-center* metric, not a wall-time fraction. Documented in
the module; the flamegraph (slice 277) remains the wall-time view.
