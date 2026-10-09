# Slice 253 — Backend hang injection

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_backend_hang.py` (8 tests, green)

## What existed before

`hugrgate/timeout.py` (slice 19) enforced per-decision deadlines via
daemon worker threads, and slice 252 added the `FaultyBackend`
wrapper with a crash mode — but nothing could script the most
insidious backend failure: the call that never returns. A hung
backend is worse than a crashed one (a crash fails fast; a hang
consumes the caller), and the timeout layer's contract — "a hung
backend becomes a `TimeoutError`, never a stuck process" — had no
fault-injection proof.

## What was built

Wired the `HANG` fault mode in `hugrgate/chaos/backend_faults.py`:

- `_inject_hang` blocks the calling thread on a never-set
  `threading.Event` (a true endless hang), or — with
  `params={"hang_s": N}` — sleeps N seconds then delegates to the
  wrapped backend (a transient hang that recovers on its own).
- `_WIRED_MODES` extended to `(CRASH, HANG)`; `arm()` validates
  `hang_s` at arm time (`None` or ≥ 0, else `SpecError`).
- Priority holds: crash still wins over hang when both fire.

## Integration

- **Timeout layer**: `TimeoutBackend(FaultyBackend(HANG),
  explicit_deadline_ms=300)` raises `TimeoutError` on schedule —
  the daemon worker is abandoned, the caller is never stuck. After
  the timeout, `disarm(HANG)` restores the backend to service; the
  hung daemon thread is abandoned per the documented
  threads-cannot-be-killed limitation shared with `hugrgate.timeout`.
- **Provenance**: hang faults count in `fault_stats()["hang"]`
  alongside crash/clean.
- Error semantics: the hang itself raises nothing (it blocks); the
  *surfaced* error is `TimeoutError` (`code "timeout"`,
  recoverable) from the existing taxonomy — no new error class.

## Verification

- 8 tests: deadline converts endless hang to `TimeoutError`
  without stalling the test; disarm-after-timeout recovery;
  transient `hang_s` delay measured (≥ 0.05 s) with correct
  delegation; arm-time param validation; seeded hang-pattern
  reproducibility; crash-over-hang priority; raw endless hang
  proven to block (daemon thread still hung after 2 s join timeout).
- `ruff check` clean.
