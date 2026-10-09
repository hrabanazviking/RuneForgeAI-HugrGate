# Slice 071 — Route simulation

## What existed
Plans could be built and executed, but never *previewed*: there was no
way to ask "what would this plan cost?" without running (and paying
for) the backends.

## What changed
- **`hugrgate/routing/simulate.py`** (new): `simulate(router, plan,
  state, ctx)` dry-runs a plan against estimates only —
  **never calls a backend** (tested with exploding backends):
  - per-rung: would-skip prediction reusing the router's real
    `skip_reason` (so predictions match execution — verified by test),
    plus estimated latency/cost/energy/memory and capability score;
  - `SimulationReport.totals()`: runnable/skipped counts, total
    latency/cost/energy, peak memory;
  - `what_if_win` table: cumulative latency/cost/energy "if rung k
    wins";
  - honest limitation stated in the report: simulation cannot predict
    *which* rung clears its gate; capability is reported as a labeled
    proxy, not a prophecy.

## Integration
Read-only over plan/registry/policy; no routing behavior changed.

## Tests
`tests/test_routing_071.py` (5 tests): skip predictions + resource
math + capability bounds, what-if cumulative table, zero backend calls
(exploding doubles), empty plan, simulation-predicted skips ==
execution skips on the same plan.

## Evidence
- `pytest tests/test_routing_071.py` → 5 passed.
