# Slice 390 — Agent privacy routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_390_privacy.py` (5 tests)

## What already existed

`hugrgate.routing.privacy` routes *backends* by privacy; the
memory gates (380/381) check classes per agent — but candidate
*filtering* for dispatch had no privacy dimension.

## What was built

- `hugrgate/agents/privacy.py` — `PrivacyRouter`: fail-closed
  candidate filtering by privacy class. Signal class from the
  payload's `privacy_class` key (default `public`, invalid
  values rejected); agent clearance from explicit
  `set_clearance` or the contract's `privacy_clearance` (376);
  unlisted agents fail closed. Nothing qualifying →
  `AgentNotFound` with the required class in details. `check()`
  is the single-agent predicate for other gates.

## Verification

`pytest tests/test_agents_390_privacy.py` — 5 passed (default
class, invalid class rejected, contract fallback, explicit
override, sorted filtering, fail-closed unknown, stats). `ruff
check` clean, `mypy` clean.
