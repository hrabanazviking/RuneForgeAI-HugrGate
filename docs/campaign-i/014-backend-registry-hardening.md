# Slice 014 — Backend registry hardening

**Date:** 2026-10-09 · **Tests:** `tests/test_backend_registry.py` (9 tests)

## Attack surface

`BackendRegistry.register` accepted anything — a non-backend, a
nameless backend, or a second backend under a taken name — and the
failure surfaced far away (`.evaluate` on the wrong object, a silently
shadowed backend). The registry is the configuration/execution trust
boundary; it now validates at the door.

## Changes (`hugrgate/backend.py`, `hugrgate/core.py`)

- `register(backend, *, replace=False)`:
  - `TypeError` for non-`Backend` objects;
  - `SpecError` for a non-string/blank name;
  - `SpecError` on duplicate name unless `replace=True` (the original
    is kept when the duplicate is rejected).
- New: `get_or_raise(name)` → `BackendUnavailable` (matches
  `HugrGate.decide`'s existing unknown-backend error);
  `unregister(name) -> bool`; `__contains__`; `__len__`.
- `HugrGate.register` passes `replace` through.

No existing registrations in the codebase or tests relied on silent
overwrite (all duplicate-name registrations were on fresh gates), so
the duplicate rule changed nothing in practice.

## Verification

9 new tests green; full suite 447 passed; mypy clean.
