# Slice 054 — Capability scoring

## What existed
Slice 053 graded backends with an inline heuristic (spec support,
accuracy claims, calibration flag) buried inside `synthesis.py` — no
factor breakdown, no reasons, and `RungBuilder(order="capability")`
silently fell back to cost ordering.

## What changed
- **`hugrgate/routing/capability.py`** (new): `CapabilityScorer` with
  weights (`CAPABILITY_WEIGHTS`: quality .35, calibration .20, features
  .20, capacity .15, spec_claim .10 — must sum to 1.0) producing
  `CapabilityScore(value, reasons, factors)`:
  - support gate: unsupported spec type → exactly 0.0 with reason;
  - quality: max of declared accuracy/reliability/quality in [0,1];
  - calibration: +bonus when `calibration_info()["calibrated"]`, minus
    declared `ece`;
  - features: coverage of `spec.metadata["requires_features"]` against
    `capabilities()["features"]`;
  - capacity: declared `limits.max_options/max_labels` vs the spec's
    value-space size; unfit → capacity factor 0.
- **`hugrgate/routing/synthesis.py`**: heuristic replaced by the scorer;
  `score_capability()` kept as a thin wrapper for earlier callers.
- **`hugrgate/routing/rungs.py`**: `order="capability"` now truly orders
  by scorer value (cost breaks ties).
- **`hugrgate/routing/__init__.py`**: exports.

## Integration
Planner-side only; execution, validation, provenance, abstention
unchanged. Scores ride in `RungNode.params["capability"]`.

## Tests
`tests/test_routing_054.py` (10 tests): zero-score gate with reason,
monotone quality response, calibration bonus vs ECE discount, feature
coverage fractions, capacity-unfit boundary, weight-sum validation,
unit-interval guarantee + weight-consistency identity, wrapper
agreement, builder capability ordering, synthesizer critical-QoS
preference. Slice-053 QoS-ordering test strengthened (calibrated
accurate backend) to reflect the reasoned scorer.

## Evidence
- `pytest tests/test_routing_051..054` → 36 passed.
