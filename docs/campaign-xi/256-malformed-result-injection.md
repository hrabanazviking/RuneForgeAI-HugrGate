# Slice 256 — Malformed-result injection

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_malformed.py` (11 tests, green)

## What existed before

`hugrgate/validation.py:validate_result` has always been the gate
that keeps out-of-spec values away from the application
(`core.py:163`), and `FaultyBackend` could crash, hang, slow, or
flakify a backend — but nothing scripted the *lying* backend: the
one that answers confidently with a value outside the decision
space, or smuggles an outside key inside its distribution. The
validation gate's contract — "the application never receives a
value outside the spec space" — had no fault-injection proof.

## What was built

Wired the `MALFORMED` fault mode in `hugrgate/chaos/backend_faults.py`
— all five backend fault modes are now live:

- `_inject_malformed` returns a `DecisionResult` that **passes the
  constructor's own invariants** but fails `validate_result`:
  - `kind="bad_value"` (default): `value="__chaos_malformed__"`,
    outside any spec space (also defeats numeric specs: not a
    number);
  - `kind="bad_distribution"`: a legal value whose distribution
    smuggles `"__chaos_outside__"`.
- `kind` validated at arm time. Priority finalized:
  crash > hang > error_rate > malformed > latency.

## Integration

- **Core validation gate**: `HugrGate.evaluate` over a malformed
  backend raises `SpecError` — the garbage never reaches the
  caller, never lands in provenance. A clean backend still passes
  the same gate (`accepted=True`).
- Error semantics: `SpecError` (`code "spec_error"`, not
  recoverable) — a malformed result is a contract violation, not a
  retryable failure.

## Verification

- 11 tests: both kinds pass the constructor but fail validation;
  numeric-spec rejection; kind validation; rate-0 cleanliness;
  seeded pattern reproducibility; priority (error_rate >
  malformed > latency); core-gate integration for both kinds;
  clean-backend control.
- The slice-252 "unwired mode" test was reworked: with all modes
  wired, it now monkeypatches `_WIRED_MODES` to prove the honest
  rejection mechanism still works.
- `ruff check` clean.
