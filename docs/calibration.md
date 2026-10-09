# Calibration

## Why

A raw model score is not a probability. Calibration maps scores to
empirically meaningful probabilities.

## Methods

- **Platt scaling** (`hugrgate.calibration.platt`): sigmoid fit on
  validation scores. Good for small validation sets.
- **Isotonic regression** (`hugrgate.calibration.isotonic`): PAV
  algorithm. More flexible, needs more data.
- **Temperature scaling** (`hugrgate.calibration.temperature`):
  single-parameter. Preserves ranking.

All implemented independently from public mathematical methods
(see `HugrGate_Plundering_Guide.md` Law 1).

## Metrics

- **Brier score**: mean squared error of probabilities.
- **Log loss**: penalizes confident wrongness.
- **ECE** (expected calibration error): binned |accuracy − confidence|.
- **MCE** (maximum calibration error): worst bin.

## Profiles

`CalibrationProfile`: named, versioned bundle of backend + calibrator +
fitted parameters + metrics + dataset hash. Stored separately from model
weights. Attached to results as `calibration_profile`.

## Drift

`DriftMonitor`: PSI (population stability index) comparing live
prediction distributions against calibration-time baselines. Alerts when
drift exceeds threshold; issues recalibration advisories.
