# Slice 337 — Confidence histograms

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_histograms.py`

## What existed

Decision probabilities were recorded per-result but never
aggregated into a distribution — no way to see where the gate's
confidence *lives*.

## What changed

- `hugrgate/observability/confidence.py`: `ConfidenceHistogram`
  over ten 0.1 bands; `mass_in()` requires 0.1-aligned band edges
  (no silent interpolation); `summary()` with per-bucket fractions
  and mean; out-of-[0,1] probabilities rejected, never clipped.
- **Statistical validation:** seeded Beta(2,2) samples (n=8000)
  reproduce the theoretical bucket masses (numeric Simpson CDF)
  within abs=0.02 on every bucket — the instrument is proven
  faithful before it is trusted. Assumptions documented: i.i.d.
  observations; faithfulness only, not gate calibration.

## Verification

Beta(2,2) bucket validation + band/mass/summary tests;
`ruff`/`mypy` clean.
