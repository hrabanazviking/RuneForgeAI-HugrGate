# Slice 345 — SLO evaluator

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_alerts_slo.py`

## What existed

SLO definitions (slice 344) with no evaluator — contracts nobody
could check.

## What changed

- `hugrgate/observability/slo_eval.py`: `SLOEvaluator` over
  timestamped windows — availability via `(timestamp, ok)` samples,
  latency via `(timestamp, ms)` against the SLO's budget. Reports
  good-fraction, burn rate (`bad_rate / error_budget`), remaining
  budget, and status: `ok` (burn ≤ 1), `warning` (1 < burn ≤ 2),
  `breaching` (burn > 2). Empty windows raise `SLOError` — an SLO
  judged on zero evidence is a configuration bug, not a passing
  grade. Injectable clock for deterministic tests.

## Verification

Covered in `tests/test_observability_alerts_slo.py` (burn-rate
verdicts at 0.5/1.5/5, window filtering, empty-window refusal,
latency kind); `ruff`/`mypy` clean.
