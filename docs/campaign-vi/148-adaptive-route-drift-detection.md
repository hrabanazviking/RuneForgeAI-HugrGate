# Slice 148 — Adaptive-route drift detection

**Status:** complete. **Tests:** `tests/test_adaptive_drift.py` — 11 tests green.

## What existed before

`hugrgate/drift.py` (slice 48) watched *calibration* distributions. Nothing
watched the *router's* behavior — route shares or reward distributions.

## What was built

`hugrgate/adaptive/drift_detect.py` — `AdaptiveRouteDriftDetector`:

- `fit_reference(events)` snapshots the reference window;
  `observe(live_events)` returns an `AdaptiveDriftReport` with PSI for
  **route drift** (per-arm traffic shares) and **reward drift** (outcome
  quality histogram), reusing `hugrgate.drift.population_stability_index`
  and the same thresholds (`PSI_WATCH=0.10`, `PSI_ALERT=0.25`) — one drift
  language across the gate.
- Shadow events excluded from both windows; empty windows refused ("no
  data" ≠ "no drift"); new arms in the live window handled via the union
  arm set.
- "action" advisories name the response playbook (retrain offline — slice
  131, counterfactual check — slice 144, rollback — slice 145) and embed
  the calibration desk's `recalibration_advisory`.

## Integration

- Drift (`population_stability_index`, `DriftReport`,
  `recalibration_advisory`), telemetry (slice 126); `SpecError` throughout.

## Verification

- `pytest tests/test_adaptive_drift.py` — 11/11 green: identical windows →
  none; 95/5 share shift → action; quality collapse → action on reward PSI;
  70/30 shift → watch (PSI ≈ 0.135 in-band); new arm → handled as action;
  shadow-only shifts invisible; serialization.
- `mypy hugrgate/adaptive` — clean.
