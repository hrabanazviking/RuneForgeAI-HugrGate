# Slice 064 — Parallel speculative rungs

## What existed
Every climb was strictly serial: one rung at a time, each paying full
latency before the next was even considered.

## What changed
- **`hugrgate/routing/parallel.py`** (new): `ParallelPlanExecutor`
  fans plan rungs across a `ThreadPoolExecutor` in waves of
  `min(options.parallel_width, qos_profile(options.qos).parallel_width)`
  — the QoS posture caps speculation (best_effort never fans out). The
  first result clearing its gate wins; losers are audited as
  below_confidence/error; pending futures are cancelled best-effort.
  Pre-run `skip_reason` checks, `_attempt` (validation + audit),
  `_log_attempt` (provenance), and all feedback hooks
  (latency/cost/energy/availability) are reused under one lock — only
  scheduling changes, never semantics. Thread-safety contract for
  `backend.evaluate` documented.

## Integration
Drop-in `RungExecutor` for `LadderRouterV2(executor=...)`; selected via
`options.strategy="parallel"`. Provenance, privacy, validation,
abstention semantics preserved; `metadata["execution"]` marks the path.

## Tests
`tests/test_routing_064.py` (8 tests): first-gate-clear beats
first-rung (timed), weak-fast loses to strong-slow, full-trace
abstention, failing backend doesn't kill the wave, width-1 serializes,
best_effort QoS never fans out (timed), unknown-backend skip, plan
fingerprint metadata + provenance store write.

## Evidence
- `pytest tests/test_routing_064.py` → 8 passed.
