# Slice 489 — Fuzz all public interfaces

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_489_fuzz.py` (8 tests)

## What existed

Fuzzing existed only in corners (privacy slice 247, security
slice 422); no generic harness covered the public entry points.

## What changed

- `hugrgate/gauntlet/fuzz.py` (new): seeded hostile-garbage
  generator (huge strings, deep nesting, NaN/Inf, wrong types,
  prototype-pollution shapes), `fuzz_callable()` (deterministic per
  seed), and `fuzz_targets()` — the curated 1.0 list:
  `DecisionSpec.from_dict`, `policy_from_dict`,
  `policy_from_compact`, `result_from_dict`,
  `result_from_compact`, `validate_state`. Only `HugrGateError`
  subclasses + stdlib validation errors may escape; anything else
  is an unexpected escape (a bug).

## Attack findings

**1800 cases across 6 targets: 0 unexpected escapes.** The entry
points are robust (slice 422's fuzz fixes hold).

## Verification

`pytest tests/test_gauntlet_489_fuzz.py` green (8 tests, incl. a
proof that the harness catches a planted `IndexError` leak);
`ruff`/`mypy` clean.
