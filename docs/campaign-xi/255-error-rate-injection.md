# Slice 255 — Error-rate injection

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_error_rate.py` (11 tests, green)

## What existed before

`FaultyBackend` (slices 252–254) could crash, hang, or slow a
backend — all-or-nothing failures. Real backends fail
*probabilistically*: the flaky GPU node that answers 7 times out
of 10. Nothing in the chaos toolkit modeled partial failure, and
nothing proved the circuit breaker actually trips under a sustained
error stream.

## What was built

Wired the `ERROR_RATE` fault mode in `hugrgate/chaos/backend_faults.py`:

- `_inject_error_rate` raises `BackendError` — the backend
  *reporting* its own inability, distinct from crash (process gone)
  and hang (no answer). `recoverable=True` per the taxonomy.
- Optional `message` param (validated non-empty at arm time).
- Priority: crash > hang > error_rate > latency (malformed lands
  in slice 256).

## Integration

- **Circuit breaker**: a `FallbackChain` with a `CircuitRegistry`
  over a 100%-erroring backend trips the breaker after
  `failure_threshold` failures — subsequent calls skip the backend
  fast (`"outcome": "skipped", "reason": "circuit_open"` in the
  fallback trace) instead of paying the error cost each time.
  This is the chaos proof that containment works: errors are
  counted, the breaker opens, failover goes quiet.
- **Fallback chain**: flaky primary → backup serves with
  `fallback_used` and `decided_by` provenance.

## Verification

- 11 tests: always-error at rate 1.0; custom message; observed
  rate 0.3 over 300 seeded calls lands in [0.2, 0.4]; seeded
  pattern reproducibility (same seed identical, different seed
  different); rate 0 clean; priority ordering across all four
  wired modes; breaker opens after 3 failures and skips fast;
  fallback routing.
- `ruff check` clean.
