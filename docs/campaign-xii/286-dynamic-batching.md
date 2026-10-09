# Slice 286 — Dynamic batching

**Status:** complete. Commit: `feat(gjallarbu-286)` on `gjallarbu/campaign-xii`.

## What existed before

Slice 285's scheduler used a fixed `max_batch_size`: optimal for one
workload, wrong for every other. Nothing adapted the batch size to
observed executor latency.

## What was built

- `hugrgate/scheduler.py`:
  - `AdaptiveBatchController`: TCP-style AIMD loop over the batch size.
    Under `target_latency_s` → additive increase (capped at
    `max_batch_size`); over → multiplicative decrease (floored at
    `min_batch_size`). Deliberate signal rule: only a *full* batch
    under target earns an increase (a half-empty fast batch says
    nothing about headroom); an over-target batch *always* decreases.
    Fully validated constructor; `snapshot()` exposes state.
  - `SchedulerConfig` gains `adaptive`, `min_batch_size`,
    `target_batch_latency_s` (all validated; `min <= max` enforced).
  - `BatchScheduler` wires the controller in: the collector uses the
    adaptive target as its cap, each batch execution feeds one
    observation, `stats()` reports `adaptive`, `effective_max_batch`,
    and the controller snapshot. Non-adaptive schedulers are
    byte-for-byte the old behavior.

## Tests

`tests/test_perf_286_dynamic_batch.py` — 12 tests: controller unit
semantics (increase/decrease/bounds/half-empty-signal rule/
over-target-always-decreases/validation), config validation, and two
end-to-end adaptations: a fast executor grows 1→8 (cap), a
latency-proportional slow executor triggers decreases and settles
below the cap. Slice-285's 20 tests still green. Ruff clean;
import-cycle test green.
