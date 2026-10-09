# Slice 203 — Node capability advertisement

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_capabilities.py` (15 tests)

## What existed before

`/backends` served backend facts for humans, but nothing described a
*node* as a routable unit: no spec-type union, no hardware facts, no
versioned advertisement peers could exchange and validate.

## What was built

- `hugrgate/cluster/capabilities.py` — `NodeCapabilities`:
  - `from_registry` / `from_gate` build the advertisement from the
    **live** `BackendRegistry` (same `capabilities()` source as
    `/backends`, plus latency/cost/remote/determinism serving facts),
    so it cannot drift from reality.
  - `matches(spec)` / `supports_backend(name)` / `spec_types()` for
    routing; `describe()` for logs.
  - `to_dict` / `from_dict` with `SpecError` on wrong protocol version
    or missing keys; hardware facts best-effort (never raise).

## Roles

Skald: `/backends` and `BackendRegistry` audited — node-level view
missing. Rúnhild: advertisement derived from registry, not hand-written.
Eldra: forged; `__version__` import uses the one sanctioned package-root
exception. Sólrún: 15 tests green. Védis: taxonomy/arch-map/manifest/
inventory regenerated. Scribe: committed `feat(gjallarbu-203)`.

## Verification

`pytest tests/test_cluster_capabilities.py` — 15 passed; ruff clean;
mypy clean.
