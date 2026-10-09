# Slice 467 — Shadow optimization mode

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_467_shadow.py` (7 tests)

## What existed

Modes jumped from offline (record-only) to live application with no
intermediate "prove it on mirrored traffic" step.

## What changed

- `hugrgate/autotune/modes.py`: `ShadowDriver` for `Mode.SHADOW` —
  every proposal's candidate config is scored *alongside* the live
  config on the same recorded samples (operator-supplied
  live/shadow scorers), producing a verdict (`would_win` /
  `would_lose` / `tie` at `min_delta`) that is journaled with both
  means and the delta. Nothing is applied, ever; a crashing scorer
  becomes `AutotuneError` and the comparison is not journaled.

## Verification

7 new tests (win/lose/tie verdicts, never-applies invariant,
scorer-crash isolation, constructor validation, controller shadow
cycle); `ruff` and `mypy` clean.
