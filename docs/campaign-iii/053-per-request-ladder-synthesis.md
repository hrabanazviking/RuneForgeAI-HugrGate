# Slice 053 — Per-request ladder synthesis

## What existed
Slice 052 built rungs dynamically but ordered them only by cost/latency
and applied one uniform gate — the same ladder for every request no
matter its QoS posture or budget.

## What changed
- **`hugrgate/routing/synthesis.py`** (new):
  - `score_capability(backend, ctx)`: heuristic in [0,1]; 0 when the spec
    type is unsupported; rewards declared accuracy/reliability, calibrated
    backends, explicit spec-type claims. (Slice 054 promotes this into a
    reasoned `CapabilityScorer`.)
  - `LadderSynthesizer(RungPlanner)`: blends capability/latency/cost with
    per-QoS weights (`QOS_WEIGHTS`), caps depth per QoS
    (`QOS_DEPTH_CAPS`: best_effort 2 … critical 8), splits
    `policy.maximum_latency_ms` fairly across rungs as per-rung budgets,
    propagates `options.strategy` into plan and nodes, and records a
    per-rung `why` plus plan `rationale`. Same registry + different QoS ⇒
    different ladder.
- **`hugrgate/routing/__init__.py`**: exports.

## Integration
Planner-only change: execution still flows through the shared v2
executor (`skip_reason` re-checks budgets at run time), provenance,
validation, and abstention semantics unchanged.

## Tests
`tests/test_routing_053.py` (8 tests): capability heuristic rewards and
zero-score boundary, QoS flipping ladder order (best_effort→fast-cheap,
critical→slow-smart), depth caps per QoS, latency-budget fair split
(sums ≤ policy max), strategy propagation, rationale populated, empty
synthesis → `Abstention`, end-to-end critical-QoS climb picks the strong
backend.

## Evidence
- `pytest tests/test_routing_053.py` → 8 passed.
