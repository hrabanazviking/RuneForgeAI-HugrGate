# Slice 387 — Agent capability registry

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_387_registry.py` (6 tests)

## What already existed

Routers (378/379) and the registry-adjacent lookups were all
ad-hoc: nothing answered "who exists, what can they do, are they
healthy" in one place.

## What was built

- `hugrgate/agents/registry.py` — `AgentRegistry`: `register()`
  validates the contract first (invalid contracts never enter);
  duplicate registration is a `ValueError` (version changes go
  through explicit unregister → register); `get()` raises
  `AgentNotFound`; `find_by_capability` / `find_by_intent` /
  `find_by_tool` with `healthy_only=True` default; `set_health()`
  flips health with a note (driven by the health router, 388).

## Verification

`pytest tests/test_agents_387_registry.py` — 6 passed
(register/get/unregister, unknown → `AgentNotFound`, invalid
contract rejected, duplicate rejected, finders, healthy-only
filtering). `ruff check` clean, `mypy` clean.
