# Slice 118 — Ensemble calibration

**Status:** complete · **Commit:** `feat(gjallarbu-118): ensemble calibration`

## Skald (inspect)
The calibration package serves single backends. Ensemble
combination rules output *scores*, not calibrated probabilities —
nothing converted vote shares into honest confidences.

## Rúnhild (design)
New module `hugrgate/ensemble/calibration.py`:
- `EnsembleCalibrator` — temperature scaling on held-out ensemble
  output distributions: `p_T(v) ∝ p(v)^(1/T)`, with T minimizing NLL
  via a deterministic golden-section search over [0.05, 10].
  - T > 1 softens overconfident ensembles; T < 1 sharpens
    underconfident ones; T = 1 is the identity.
- `fit` records ECE/NLL before/after; `calibrate` maps a
  distribution; `calibrate_result` returns a calibrated
  `DecisionResult` with `calibration_profile="ensemble:temperature"`,
  recomputed uncertainty, preserved ensemble metadata, and a
  calibration block (temperature, ECE before/after).
- `expected_calibration_error(distributions, labels)` — bench's
  formula, distribution-native.

## Eldra (code)
Pure-stdlib math; abstentions pass through unchanged.

## Sólrún (tests)
`tests/test_ensemble_118_calibration.py` — 10 tests green:
success (overconfident 0.9/60% → T≈5.42, ECE 0.30→0.00, exact
calibrated 0.6/0.4; calibrated data → T≈1.0; deterministic fit;
end-to-end calibrate_result preserving metadata;
abstention passthrough; ECE unit; to_dict),
failure (use-before-fit BackendError; all fit validations),
boundary (temperature within search bounds).
mypy clean.

## Védis (integrate)
- `EnsembleCalibrator`, `expected_calibration_error` exported;
  documented calibration-after-combination pattern.

## Scribe
Committed `feat(gjallarbu-118): ensemble calibration`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/calibration.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_118_calibration.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_118_calibration.py -q` → 10 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
