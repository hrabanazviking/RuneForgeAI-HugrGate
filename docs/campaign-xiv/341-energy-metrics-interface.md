# Slice 341 — Energy metrics interface

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_domain_metrics.py`

## What existed

`RouteEvent.energy_wh` existed in the telemetry log with no live
aggregation and no documented estimation story.

## What changed

- `hugrgate/observability/energy.py`:
  - `EnergyEstimator` protocol — operators plug in RAPL/nvidia-smi
    readers here.
  - `DefaultEnergyEstimator` — deterministic power-coefficient model
    (`Wh = watts × hours`); `describe()` always reports the
    coefficient table and its caveat so estimates are never mistaken
    for meter readings.
  - `EnergyMetrics` — aggregation by backend with metered-value
    override, mirroring `CostMetrics`.
- `benchmarks/observability_energy_341.py` →
  `benchmarks/observability_energy_341.json`: honest artifact —
  coefficient provenance ("NOT a meter reading"), determinism
  check, worked example vs. a zero-power baseline. What is *not*
  claimed: these numbers are not hardware truth.

## Verification

Estimator math, override path, artifact-honesty tests;
`ruff`/`mypy` clean.
