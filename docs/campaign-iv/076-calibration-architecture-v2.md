# Slice 076 — Calibration architecture v2

## What existed
Three binary calibrators (Platt / isotonic / temperature), bare metrics
(Brier, log-loss, ECE, MCE), and versioned `CalibrationProfile`s — but no
lifecycle around fitting: no fit-data diagnostics, no before/after
comparison, no way to refuse a calibration that made things worse.

## What changed
- `hugrgate/calibration/pipeline.py` (new):
  - `validate_fit_data(scores, labels)` — hard validation (non-empty,
    length match, finite scores, 0/1 labels, ≥ `MIN_FIT_SAMPLES` = 10 rows,
    **both classes present**) returning `FitDiagnostics` (counts,
    score range, positive rate, SHA-256 dataset hash).
  - `CalibrationPipeline(factory)` — fit → before/after metrics → report.
    `fit_strict()` raises `CalibrationError` when the fit did not genuinely
    improve Brier (beyond 1e-9 solver noise) without regressing ECE.
  - `CalibrationReport` — JSON-serializable before/after record with
    provenance, dataset hash, `improved` verdict, `improvement(metric)`.
- `hugrgate/calibration/__init__.py` — exports `pipeline` module members.

## Statistical validation
Controlled miscalibrated data (true p = σ(z), reported = σ(2z), n = 400):
all three calibrators show `improved == True` with positive Brier and ECE
improvement. Assumption: before/after metrics are **in-sample**; a
1-parameter fit can eke out tiny in-sample Brier gains via optimism, hence
the 1e-9 gain floor and the documented recommendation to pair the pipeline
with the slice-092 auto-selection cross-validation before production
deployment.

## Tests
`tests/test_calib_pipeline.py` — 8 tests, all green.
`~/workspace/RuneForgeAI-HugrGate/venv/bin/python -m pytest tests/test_calib_pipeline.py -q`
