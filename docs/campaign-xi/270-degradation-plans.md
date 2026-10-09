# Slice 270 — Degradation plans

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_degradation.py` (11 tests, green)

## What existed before

The chaos toolkit could *cause* every failure mode, and slices
268–269 could bound retries and isolate concurrency — but nothing
said what the system should *do* when a failure mode arrived. The
response was improvised per call site.

## What was built

**`hugrgate/chaos/degradation.py`** (new module, exported from
`hugrgate.chaos`):

- **`DegradationStep`** — name, description, `run(context) -> note`
  (a `"SKIP: ..."` note marks the step skipped when its
  precondition isn't met).
- **`DegradationPlan`** — name, description, `triggers` (taxonomy
  failure codes it answers), ordered steps; validated
  (non-empty, ≥1 trigger, ≥1 step, unique step names).
- **`DegradationPlanRegistry`** — `register`/`get`/`names`/
  `plans_for(failure_code)`/`execute(name, context,
  failure_code)`.
- **`DegradationReport`** — per-step outcomes, `outcome` in
  {full, partial, none}, `degraded_gracefully`, JSON-serializable
  `to_dict()`.

**Execution is best-effort:** a raising step is recorded as failed
and the plan continues — a degradation plan that aborts halfway
is worse than none.

**Builtin plans** (`builtin_degradation_plans()`), wired to real
collaborators via context callables:

- `serve-stale-cache` (triggers `backend_unavailable`,
  `backend_error`, `timeout`, `retry_budget_exhausted`):
  probe the `DecisionCache`, then abstain with reason.
- `failover-then-abstain` (triggers `backend_unavailable`,
  `bulkhead_rejected`): try the standby chain, then abstain.

Every builtin plan's last resort is an explicit, reasoned
abstention — never a silent wrong answer.

## Verification

- 11 tests: registry mechanics (duplicates, unknown, trigger
  matching), plan/step validation, continue-past-failure,
  skip semantics, empty outcome, and builtin plans wired to a
  **real** `DecisionCache` (hit → stale served; miss → abstain)
  and a **real** `FallbackChain` (failover served; total outage →
  explicit abstain).
- `test_api_inventory.py`, import-cycle gate, `ruff check` —
  all green (one transient failure in an earlier combined run
  did not reproduce across four re-runs).
