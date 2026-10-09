# Slice 268 — Retry budget

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_retry_budget.py` (13 tests, green)

## What existed before

No retry loops exist in production code — retries were unbounded
by construction, living only in callers' heads. A flapping backend
could turn one bad call into a self-inflicted DoS with nothing to
stop it.

## What was built

**`hugrgate/chaos/retry.py`** (new module, exported from
`hugrgate.chaos`):

- **`RetryBudget`** — fixed-window token bucket: `max_retries`
  tokens per `window_s` (default 60s), injectable clock,
  thread-safe. First attempt is always free; each *retry* consumes
  one token; the window refills on lapse. `stats()` for
  observability.
- **`retry_with_budget(fn, budget, *, is_retryable, on_retry)`** —
  executor. Non-retryable failures propagate immediately without
  touching the budget; when the budget is spent it raises
  **`RetryBudgetExhausted`** (chaining the last failure) with
  `attempts` and `last_error_code` details.
- **`default_retry_policy`** — retries taxonomy errors that
  declare themselves `recoverable`; never argument errors;
  excludes `RetryBudgetExhausted` itself (a budget verdict is
  final at its own level).

**New taxonomy error** `RetryBudgetExhausted` in
`hugrgate/errors.py` — code `retry_budget_exhausted`,
`recoverable=True`, subclass of `BackendError` so it flows
through existing backend-failure handlers unwrapped (distinct
`code` preserves the specifics). Registered in
`tests/test_errors.py` (import, `ALL_ERRORS`, code map,
recoverable map).

**Integration:** `HugrGate.decide(..., retry_budget=None)` and
`adecide` accept an optional budget. `None` (default) keeps the
exact single-attempt behavior — zero change for existing
callers; with a budget, transient backend faults are retried
within it.

## Verification

- 13 tests: acquire/refill with a fake clock (including the
  not-yet-lapsed window edge), argument validation, thread-safety
  (8 threads × 25 acquire → exactly 100 tokens), retry success
  within budget, exhaustion details + chaining + `BackendError`
  lineage, non-retryable bypass (SpecError: 1 attempt, budget
  untouched), custom policy, default-policy truth table, and
  four `decide`-level tests: no-budget single attempt, budget
  exhaustion (3 attempts, budget spent), success without
  consumption, transient fault ridden out (1 retry consumed).
- `test_errors.py` (incl. the raise-site gate), import-cycle
  gate, and `ruff check` all green.
