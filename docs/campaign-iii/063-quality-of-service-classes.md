# Slice 063 — Quality-of-service classes

## What existed
Slice 053 scattered QoS posture across two module-level dicts
(`QOS_DEPTH_CAPS`, `QOS_WEIGHTS`) in `synthesis.py`; nothing else in
routing knew about QoS, and there was no notion of posture beyond
depth/weights.

## What changed
- **`hugrgate/routing/qos.py`** (new): `QoSClass`
  (best_effort/standard/priority/critical), frozen `QoSProfile`
  (depth_cap, blend weights, parallel_width, hedge_allowed,
  hedge_delay_ms, fast_path_probability, early_exit_delta),
  `QOS_PROFILES` table, `qos_profile(name)` with strict parsing.
  Posture strengthens monotonically: critical gets depth 8, width 4,
  hedging, and 0.8 capability weight; best_effort gets depth 2, no
  hedging, cost/latency-leaning weights.
- **`hugrgate/routing/synthesis.py`**: the 053 dicts are now derived
  views over `QOS_PROFILES` (single source of truth); the synthesizer
  reads the profile. Backward-compatible names kept.

## Integration
`RoutingOptions.qos` validation unchanged; profiles are the contract
slices 064–066 (parallel width, hedge delay/allowance, fast-path bar)
will consume.

## Tests
`tests/test_routing_063.py` (6 tests): parse + invalid rejection,
profile sanity (weights sum to 1, monotonic posture, hedge flags),
profile validation errors, dict/profile agreement, synthesizer depth
caps per class, options validation.

## Evidence
- `pytest tests/test_routing_063.py tests/test_routing_053.py` →
  14 passed.
