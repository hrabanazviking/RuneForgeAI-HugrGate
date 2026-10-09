# Slice 475 — Autonomous Optimization release gate

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_475_release.py` (7 tests)

## What existed

The campaign had 24 slices of capability and no final verdict: no
single place answered "is Campaign XIX shippable".

## What changed

- `hugrgate/autotune/release.py`: `release_gate()` runs six checks
  in order — error-taxonomy registration, controller smoke,
  safety posture (kill switch off, APPLIED excluded by default),
  provenance record+verify round-trip, manifest record+replay
  match, tuner module imports — and returns a `ReleaseVerdict`
  (`release`/`hold` with every reason named). A crashing check
  *holds* (never crashes the gate); zero checks is refused as a
  rubber stamp; `assert_release()` turns a hold into
  `AutotuneError` for CI.
- `docs/campaign-xix/AUTONOMOUS-OPTIMIZATION-REPORT.md`: the
  campaign completion report — 25-slice log, 231 new tests, the
  four genuine findings (including the 40% label-noise breaking
  point), and open debt threads.
- `CHANGELOG.md`: additive Campaign XIX "Unreleased" section
  (README prose untouched).

## Verification

The gate itself passes on the finished campaign (all six checks
green, verified live). 7 new tests (gate passes, holds on failure,
crashing check holds, zero checks refused, assert semantics,
serialization, check names); `ruff` and `mypy` clean.
