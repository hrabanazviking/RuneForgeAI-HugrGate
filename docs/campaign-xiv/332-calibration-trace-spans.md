# Slice 332 — Calibration trace spans

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_spans.py`

## What existed

Calibration ran and reported coverage numbers, but nothing rendered a
calibration step as a span, and no test validated that a claimed
coverage was statistically believable.

## What changed

- `hugrgate/observability/spans_calibration.py`:
  - `calibration_span()` + `annotate_calibration()` — method,
    nominal/achieved coverage, sample count (never raw labels/scores).
  - `empirical_coverage()` — fraction of prediction sets containing
    the true label on controlled labeled data, with strict input
    validation (a coverage number on malformed input is worse than
    no number).
  - `coverage_within_tolerance()` — judges achieved vs. nominal
    coverage with an **exact Clopper-Pearson binomial confidence
    interval** (log-space implementation: no `math.comb` overflow,
    no float underflow), never eyeballing.
  - Documented metric/coverage assumptions: i.i.d. samples; `n` is
    the *labeled holdout* count, never training count; under
    distribution shift the interval is optimistic.

## Verification

Seeded controlled-data test: a 90%-accurate synthetic calibrator
(n=2000) validates within tolerance; a 50% calibrator is rejected;
CI implementation checked against textbook values (5/10 →
0.187–0.813); `ruff`/`mypy` clean.
