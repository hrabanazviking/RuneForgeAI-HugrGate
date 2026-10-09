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
# noexec: illustrative fragment — needs calibration_confidences in scope
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

## Calibration Forge (Campaign IV, slices 076–100)

The calibration package grew from three point calibrators into a full
forge. New modules (all under `hugrgate.calibration`):

**Lifecycle & fitting.** `pipeline` — `CalibrationPipeline`: fit-data
diagnostics, before/after Brier/log-loss/ECE/MCE report, `fit_strict`
refuses non-improving fits. `perclass` — one-vs-rest multiclass fitting
with per-class metrics and constant-prior fallback for unseen classes
(`build_profile` feeds `CalibrationProfile`). `group` — per-group
calibrators with a calibration-disparity (fairness-gap) report.

**Adaptive.** `online` — incremental binned calibration with exponential
forgetting. `window` — refits any batch calibrator on a sliding window.
`drift` — `CalibrationDriftMonitor`: EWMA control chart over batch Brier
*and* ECE of calibrated outputs; recommends `recalibrate` on alarm.

**Under data trouble.** `imbalance` — seeded rebalancing, Saerens prior
correction, stratified metrics. `shift` — PSI shift detection, binned
density-ratio weights / resampling for covariate shift, Saerens EM target
prior for label shift.

**Conformal & sets.** `conformal` — split-conformal classification
(incl. Mondrian group-conditional mode). `conformal_regression` —
constant-width and difficulty-weighted intervals. `sets` —
`PredictionSet` abstraction (threshold / top-k / cumulative-mass /
conformal) with coverage and size-stratified coverage metrics. `coverage`
— Clopper-Pearson / Hoeffding tooling and `CoverageCertificate`s.

**Selection & curves.** `selective` — selective accuracy curves, AUSC,
coverage/accuracy lookups. `risk_coverage` — risk-coverage curves, AURC,
oracle regret, `coverage_at_risk` abstention lookup. `registry` — rich
metadata catalog over the calibrator registry (family, monotonicity,
streaming, deprecation). `autoselect` — seeded K-fold CV calibrator
selection. `ensemble` — weighted mean/median of member maps.

**Uncertainty.** `decomposition` — total = aleatoric + epistemic
(mutual information). `epistemic` — ensemble MI, score-cloud distance
OOD proxy, review gate into `hugrgate.abstain`. `aleatoric` — predictive
entropy, Bernoulli noise, binned label-noise floor.

**Assurance.** `adversarial` — over/underconfidence, label-flip and bias
attacks with `stress_test` degradation reports. `bench` +
`benchmarks/build_calibration.py` — reproducible benchmark suite;
artifact `benchmarks/calibration_500.json` (measured, never invented).
`viz` — JSON visualization payloads (reliability curves, histograms,
per-class ECE, dashboard).

Registry names: `platt`, `isotonic`, `temperature`, `online`,
`sliding-window`, `beta-binomial` (research adapter with credible
intervals), `constant-prior`, `ensemble`. Per-slice notes live in
`docs/campaign-iv/076-*.md` … `docs/campaign-iv/100-*.md`.
