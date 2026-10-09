# Slice 488 — Long-duration soak

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_488_soak.py` (7 tests)

## What existed

`hugrgate/chaos/soak.py` could soak for hours without noticing a
slow memory leak — no invariant watched memory.

## What changed

- `hugrgate/gauntlet/soak.py` (new): `rss_mb()` (guarded
  `resource.getrusage`; None when unobservable),
  `MemoryGrowthInvariant` (a `SoakRunner` invariant: snapshots RSS,
  raises past `budget_mb` growth, refreshes the snapshot every
  `window_ops` checks so warmed-up caches don't false-positive),
  `run_gate_soak()` (real `HugrGate.decide` loop under
  `SoakRunner` with the invariant armed).
- `tools/soak_run.py` (new, executable): runnable soak CLI.

## Verification

`pytest` green; live soak: **3000 ops, max RSS growth 0.2 MiB,
0 violations, 0 errors — SOAK PASS**; `ruff`/`mypy` clean.
