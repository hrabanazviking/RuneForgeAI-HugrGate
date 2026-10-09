# Slice 052 — Dynamic rung construction

## What existed
Rung lists were statically configured at router construction
(`LadderRouter(rungs=[...])` / per-type `ladders={...}`); the only
per-request adaptation was plan-time skipping. Nothing built a ladder
from the live registry.

## What changed
- **`hugrgate/routing/rungs.py`** (new):
  - `RungBuilder`: `candidates(registry, ctx)` enumerates the registry and
    applies built-in filters (policy allowlist, `supports(spec)`, remote
    pre-filter via `policy.backend_allowed`) plus pluggable
    `extra_filters`; survivors sort cheapest-first (`order="cost"`),
    fastest-first (`order="latency"`), or capability-first (reserved for
    the slice-054 scorer, falls back to cost). `preferred_backends` float
    first. `build()` emits `RungNode`s inheriting the policy's
    `minimum_probability` gate and `maximum_latency_ms` budget, each with
    a human-readable `why`.
  - `DynamicRungPlanner`: `RungPlanner` adapter producing a
    `RoutingPlan(created_by="DynamicRungPlanner")` per request.
- **`hugrgate/routing/__init__.py`**: exports `RungBuilder`,
  `DynamicRungPlanner`, `RungFilter`.

## Integration
Executor-side `skip_reason` re-checks privacy/latency at run time, so a
policy change between planning and execution stays safe. Validation,
provenance, and error semantics flow through the shared `_attempt` path.

## Tests
`tests/test_routing_052.py` (10 tests): cost/latency ordering, preferred
float, allowlist + unsupported pruning, remote pre-filter both ways,
`max_rungs` cap, empty registry, invalid args, extra filter plug-in,
policy gate/budget inheritance, end-to-end dynamic climb (weak rung below
gate → strong rung wins), empty dynamic plan → `Abstention`.

## Evidence
- `pytest tests/test_routing_051.py tests/test_routing_052.py
  tests/test_ladder.py` → 80 passed.
