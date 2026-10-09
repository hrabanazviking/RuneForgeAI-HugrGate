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

`DriftMonitor` (`hugrgate.drift`): PSI (population stability index)
comparing live prediction distributions against calibration-time
baselines. Two modes:

```python
from hugrgate.drift import DriftMonitor, recalibration_advisory

# Histogram mode: confidence distribution vs calibration time.
monitor = DriftMonitor(alert_threshold=0.25)
monitor.fit_reference(calibration_confidences)
report = monitor.observe(live_confidences)   # DriftReport: psi, alert, severity
if report.alert:
    print(recalibration_advisory(report))    # concrete next steps

# Streaming mode: per-prediction observations.
monitor.observe("escalate", 0.92)
...
if monitor.check_drift():                    # PSI over label frequencies
    print("label drift:", monitor.psi())
```

Thresholds follow the industry rule of thumb: PSI < 0.10 no drift,
0.10–0.25 watch, ≥ 0.25 significant drift → recalibration advised.
Alerts below `min_live_samples` (default 30) are suppressed.
