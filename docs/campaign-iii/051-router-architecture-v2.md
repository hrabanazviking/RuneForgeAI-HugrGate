# Slice 051 — Router architecture v2

## What existed
`LadderRouter` (slices 31-32) interleaved rung selection with execution:
the climb loop chose rungs, pruned them, ran them, and gated them inline.
There was no inspectable plan object, no planner/executor separation, and
the four pre-run pruning checks (unknown backend, unsupported spec,
privacy block, latency budget) were inline in `decide()`.

## What changed
- **`hugrgate/ladder.py`** (Anti-Checkbox hardening, not duplication): the
  four pruning checks extracted into `LadderRouter.skip_reason(backend,
  rung, spec, policy, started) -> Optional[(outcome, detail)]`; `decide()`
  now calls it. Behavior unchanged — all 62 existing ladder tests green.
- **New package `hugrgate/routing/`**:
  - `architecture.py`: `RungMode` (serial/parallel/hedged), `RoutingOptions`
    (per-request knobs: qos, strategy, budgets, privacy tier, hedge delay,
    parallel width, fast-path, early-exit delta, record, seed — all
    validated, invalid values raise `PolicyError`/`SpecError`),
    `RouterContext` (planner input carrying state *shape* only, never raw
    values), `RungNode`, `RoutingPlan` (stable sha256 `fingerprint`),
    `RoutingDecision`, `RungPlanner`/`RungExecutor` protocols,
    `SerialPlanExecutor` (v2 serial climb reusing `skip_reason`/`_attempt`),
    `LadderRouterV2(LadderRouter)` with `build_plan()` (side-effect free,
    inspectable) and `decide(..., options=...)`.
- **`hugrgate/routing/__init__.py`**: public exports.

## Integration
Policy, validation, provenance, privacy, error semantics unchanged and
reused: v2 execution calls the same `_attempt` (validation + audit) and
`_log_attempt` (provenance + redaction) as v1. `Abstention` on exhaustion
now also carries `plan_fingerprint`.

## Tests
`tests/test_routing_051.py` (8 tests): options/node validation incl.
boundaries, plan determinism + no side effects, no raw-state leakage into
context, fingerprint stability/sensitivity, v2-serial == v1 outcomes,
exhaustion abstention with plan fingerprint, `skip_reason` reuse, custom
planner/executor plug-in.

## Evidence
- `pytest tests/test_routing_051.py tests/test_ladder.py` → 70 passed.
