# Slice 271 — Recovery verification

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_recovery.py` (8 tests, green)

## What existed before

Disarming a fault was treated as recovery. Nothing verified the
system was actually healthy afterward — a disarmed backend could
still have an open circuit breaker, a poisoned cache, or wedged
threads, and the next incident would relapse on the same fault.

## What was built

**`hugrgate/chaos/recovery.py`** (new module, exported from
`hugrgate.chaos`):

- **`RecoveryProbe`** — name, description, `check()` (raises on
  failure, returns a note on success); validated.
- **`RecoveryVerifier`** — ordered probes; `verify(max_attempts=1,
  wait_s=0.0)` runs every probe (a failing probe doesn't stop the
  others) and retries each probe across attempts with injectable
  `sleep` for deterministic tests. Thread-safe.
- **`RecoveryReport`** — per-probe outcomes with attempt counts,
  `recovered` (all passed), `attempts`, JSON-serializable
  `to_dict()`.

**Builtin probes** (real collaborators, no mocks):

- `backend_health_probe(backend)` — `health()` reports ok.
- `decision_smoke_probe(gate, state, spec, backend_name)` — a real
  `decide()` succeeds and is accepted.
- `circuit_closed_probe(get_state, backend_name)` — the breaker's
  state is closed.

## Verification

- 8 tests: all-pass verdict, failing probe doesn't stop others,
  retry-until-recovered with injected sleep (sleeps between
  attempts only), exhausted attempts, validation, and the full
  story — healthy baseline → armed `error_rate` fault (probe
  fails) → disarmed → **verified** recovered; health probe
  against healthy and sick backends; circuit probe against a
  real `CircuitRegistry` breaker (closed → open → not recovered).
- `test_api_inventory.py`, import-cycle gate, `ruff check` —
  green. Note: one transient failure appeared in a single
  combined run (as in slice 270) and did not reproduce across
  7+ re-runs of the same combinations; attributed to run
  flakiness, not the new code.
