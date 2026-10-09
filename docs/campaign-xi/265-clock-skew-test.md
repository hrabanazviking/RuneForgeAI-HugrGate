# Slice 265 — Clock-skew test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_clock_skew.py` (5 tests, green)

## What existed before

Deadlines, TTLs, breaker timeouts, and watchdog intervals were
*believed* monotonic, but nothing verified the belief — and wall
clock does jump (NTP steps, VM pauses). A single `time.time()`
smuggled into a deadline path would silently turn clock skew into
hung decisions or premature failovers.

## What was built

`hugrgate/chaos/clock.py`:

- **`SkewedClock`** — a test clock that jumps: wraps a base clock,
  `jump(±seconds)` applies an instantaneous NTP-style step,
  `advance()` moves smoothly; usable anywhere a `clock=` callable
  is accepted.
- **`audit_deadline_clocks()`** — inspects the live code and
  reports which clock each resilience-critical component uses.
  A regression tripwire: rewiring a deadline to the wall clock
  fails the audit's test until done deliberately.

## Audit result

Every enforcement path is monotonic:

| Component | Clock |
|---|---|
| `CircuitRegistry` / `CircuitBreaker` | `time.monotonic` (injectable default) |
| `ExperimentRunner` | `time.monotonic` (injectable default) |
| `EdgeWatchdog` | `time.monotonic` (`None` → monotonic) |
| `DecisionCache` TTL | `time.monotonic()` direct (source tripwire) |
| `run_with_deadline` | relative `thread.join` (inherently monotonic) |

Known wall-clock *durations* (audited, accepted — bounded,
self-healing, never decision-affecting): delayed-label expiry
(`adaptive.delayed`), peer staleness (`cluster.discovery` —
backward jump keeps a dead peer, forward jump drops a live one,
both heal on next heartbeat), LAN announce cadence. Wall clock
remains correct for *timestamps* (human-readable records).

## Verification

- 5 tests: `SkewedClock` jump/advance/callable semantics;
  audit asserts monotonic for all 5 components (fails on any
  `UNEXPECTED`); injected clocks are *followed* (breaker obeys a
  jumped clock — proving the injection point works and the
  monotonic default is what immunizes production); peer
  staleness under ±1h skew documents the accepted degradation.
- `test_import_cycles.py` re-run green (no new cycles).
- `ruff check` clean.
