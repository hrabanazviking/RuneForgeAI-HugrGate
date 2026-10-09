# Slice 252 — Backend crash injection

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_backend_crash.py` (15 tests, green)

## What existed before

`FallbackChain` (slice 14) already failed over on `BackendError`,
and the circuit breaker (slice 18) contained failing backends — but
nothing could *script* a backend dying. Crash resilience was
asserted with hand-rolled raising stubs, never with a seeded,
reproducible fault injector integrated into the backend contract.

## What was built

`hugrgate/chaos/backend_faults.py` — `FaultyBackend`, a transparent
`Backend` wrapper (name, capabilities, `supports`, `health`,
`is_remote` all delegate):

- **CRASH mode**: `evaluate` raises `BackendUnavailable`
  ("chaos: injected crash of backend …"). Crash is
  `recoverable=True` per the taxonomy — failover or retry can
  succeed — so the fallback chain treats it as a routing event, not
  a verdict.
- **Fault arming**: `arm(FaultSpec(mode, rate, seed, params))`,
  `disarm` / `disarm_all`, `armed_modes()`. Rates are validated to
  [0, 1]; each mode rolls against its own seeded `random.Random`,
  so crash patterns are reproducible run to run.
- **Priority**: when several modes fire on one call,
  crash > hang > error_rate > malformed > latency.
- **Accounting**: `fault_stats()` counts per-mode faults plus clean
  calls; thread-safe under concurrent `evaluate`.
- **Honesty gate**: arming a mode whose injector is not wired yet
  (hang/latency/error-rate/malformed land in slices 253–256) raises
  `SpecError` naming the wired modes — silent non-firing is
  forbidden.

## Integration

- Fallback chain: a crashed primary routes to the secondary;
  `result.fallback_used` is set and `metadata["fallback_trace"]`
  records the `BackendUnavailable` on the primary. When *every*
  backend crashes, the policy's `fallback_behavior` decides
  (abstain in the test).
- Error semantics: `BackendUnavailable` (`code
  "backend_unavailable"`, recoverable) — no new error class needed.
- Privacy/provenance: no new data collected; fault counts live only
  in memory on the wrapper.

## Verification

- 15 tests: always/never crash, taxonomy recoverability, seed
  reproducibility (same seed → identical 20-call pattern; different
  seed → different), spec validation, unwired-mode rejection,
  arm/disarm/re-arm lifecycle, transparency, stats reset,
  4-thread × 50-call stats consistency, fallback-chain survival,
  all-crashed abstention.
- `ruff check` clean on the new module and tests.
