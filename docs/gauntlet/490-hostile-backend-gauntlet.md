# Slice 490 — Hostile backend gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_490_hostile.py` (11 tests)

## What existed

The gate claimed total backend containment, but `_translate_backend_error`
caught only `Exception`: a hostile backend raising raw
`BaseException` / `KeyboardInterrupt` / `SystemExit` propagated
uncaught. `_finalize_result` also touched `result.latency_ms`
before any type check, so a backend returning a string leaked
`AttributeError`.

## What changed

- `hugrgate/core.py`: `except BaseException` → chained
  `BackendError` in `_translate_backend_error` **and** in the
  async path's inline handler (same gap, was not shared code);
  `_finalize_result` now fails closed with `BackendError` on
  non-`DecisionResult` returns.
- `hugrgate/gauntlet/hostile.py` (new): 10 hostile doubles
  (exploding, raw BaseException, KeyboardInterrupt, SystemExit,
  NaN, wrong-type, None, out-of-space, bad-distribution).

## Verification

`pytest tests/test_gauntlet_490_hostile.py` green — every hostile
double is contained (chaining verified via `__cause__`);
`Abstention` and `BackendError` subclasses still propagate
unchanged; existing foundation/config suites green;
`ruff`/`mypy` clean.
