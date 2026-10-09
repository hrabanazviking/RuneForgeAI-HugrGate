# Slice 134 — Energy-quality objective

**Status:** complete. **Tests:** `tests/test_adaptive_energy_quality.py` — 6 tests green.

## What existed before

Energy was not a routing consideration anywhere in the repo.

## What was built

`hugrgate/adaptive/energy_quality.py`:

- `EnergyQualityObjective`: `score = w_q·quality − w_e·(energy_wh/energy_scale)`.
- `estimate_energy_wh(latency_ms, watts)`: `watts · latency_s / 3600` —
  energy from *measured* latency × a power model, not vibes.
- `DEFAULT_LOCAL_WATTS = 150.0` / `DEFAULT_REMOTE_WATTS = 25.0`:
  conservative, documented estimates (callers with real power telemetry
  pass their own watts).
- `measure_energy(fn, watts, n_runs, label)`: pairs slice-133's latency
  measurement with the power model into an `EnergyMeasurement` artifact
  (mean_wh, p95_wh derived from measured latency).

## Integration

- Implements slice-132's `RouteObjective`; reuses slice-133's measurement
  machinery; `SpecError` on bad weights/scale and non-physical inputs.

## Verification

- `pytest tests/test_adaptive_energy_quality.py` — 6/6 green: leaner wins
  at equal quality, Wh math (150W × 1h = 150Wh), measured artifact whose
  mean_wh equals `estimate_energy_wh` of the *measured* mean latency,
  quality/energy trade-off.
- `mypy hugrgate/adaptive` — clean.
