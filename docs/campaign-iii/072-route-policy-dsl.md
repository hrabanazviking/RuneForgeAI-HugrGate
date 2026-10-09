# Slice 072 — Route policy DSL

## What existed
Routing posture lived in code: `RoutingOptions(...)` and
`DecisionPolicy(...)` constructor calls. Operators had no declarative
surface.

## What changed
- **`hugrgate/routing/dsl.py`** (new): a tiny `route { ... }` language.
  - Statements: `qos`/`strategy`/`privacy_tier`/`privacy` identifiers;
    numeric knobs (`max_cost`, `max_energy_j`, `max_memory_mb`,
    `max_latency_ms`, `min_probability`, `hedge_delay_ms`,
    `parallel_width`, `fast_path`, `early_exit_delta`);
    `prefer`/`allow`/`forbid` backend lists; the conditional
    `skip remote when privacy = strict`.
  - `parse(text) -> RoutePolicy`; `RoutePolicy.apply(policy, options)`
    merges onto a base pair (DSL wins); `dumps()` renders back to
    round-trippable DSL.
  - Errors carry line numbers; unknown keys, duplicates, bad shapes,
    and invalid values raise `PolicyError`/`SpecError`. Validity is
    enforced by materializing the real `RoutingOptions`/`DecisionPolicy`
    objects, so the DSL cannot express an invalid configuration.

## Integration
`parse_route_policy` exported from `hugrgate.routing`; output feeds
`LadderRouterV2.decide(..., options=...)` directly (tested end to end).

## Tests
`tests/test_routing_072.py` (7 tests): full-example parse fidelity,
apply-merge precedence (DSL wins, forbid prunes allowlist, options vs
policy level placement), conditional remote rule firing/not firing,
comments + minimal policy, seven error cases, dumps round-trip,
end-to-end router drive.

## Evidence
- `pytest tests/test_routing_072.py` → 7 passed.
