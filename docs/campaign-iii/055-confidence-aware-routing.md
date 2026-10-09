# Slice 055 — Confidence-aware routing

## What existed
Rung gates (`min_confidence`, policy `minimum_probability`) trusted
reported probabilities at face value. Nothing accounted for backend
miscalibration — an overconfident backend cleared gates it had not
earned.

## What changed
- **`hugrgate/routing/confidence.py`** (new):
  - `CalibrationTracker`: per-backend `(probability, correctness)` ledger;
    `ece()` computes expected calibration error over 10 equal-width bins
    (Σ |acc − conf| · n/N); `gate_for(name, base)` widens additively.
  - `adjusted_gate(base, ece)`: widen + clamp to [0,1]; never lowers a
    gate; validates inputs.
  - `ConfidenceAwarePlanner`: wraps any `RungPlanner`; rewrites each
    rung's gate by the backend's ECE — measured tracker ECE once
    `min_samples` (50) exist, else the declared
    `calibration_info()["ece"]`, else 0. Unknown backends pass through
    untouched. Records `ece`/`base_gate` in node params and annotates
    `why`.

## Statistical validation (controlled data, fixed seeds)
- Overconfident backend (reports 0.9, true 0.7, n=5000): measured
  ECE ≈ 0.2 (±0.03); gate 0.8 → ≈1.0.
- Calibrated backend (p∼U[0.5,1], correct∼Bernoulli(p), n=20000):
  ECE < 0.03; gate unchanged within 0.03.
- Coverage: decisions accepted at gate 0.8 from the calibrated backend
  are correct ≈0.9 (±0.03) ≥ 0.78 — the gate's coverage assumption holds.

## Integration
Planner-side only; execution, validation, provenance, privacy, and
abstention semantics unchanged.

## Tests
`tests/test_routing_055.py` (8 tests): gate widen/clamp/validation,
tracker input validation, declared-ECE widening with `why` annotation,
measured-ECE overriding declared ECE, unknown-backend passthrough, plus
the three statistical validations above.

## Evidence
- `pytest tests/test_routing_055.py` → 8 passed.
