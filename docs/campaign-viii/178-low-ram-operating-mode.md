# Slice 178 — Low-RAM operating mode

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_memory.py` (13 tests, green)

## What existed before

Slice 177 baselines record how much RAM a board *has*; nothing modeled
how little RAM a runtime may *use*, or what happens when headroom
evaporates mid-inference.

## What was built

`hugrgate/edge/memory.py`:

- **`MemoryMode`** — `standard | low | critical`, derived from
  available bytes: `< 256 MiB` → critical, `< 1024 MiB` → low
  (boundary pinned by test: exactly-at-threshold stays in the higher
  mode).
- **`MemoryManager`** —
  - `probe()` parses `/proc/meminfo` (`MemAvailable`, with a
    `MemFree+Buffers+Cached` fallback for ancient kernels), honors
    cgroup v1/v2 limits, degrades gracefully when `/proc` is absent;
  - `refresh()` re-derives the mode and fires `on_mode_change(old,
    new)` callbacks in registration order, only on actual change;
  - `budget_bytes(component)` / `budgets()` give per-mode fractional
    budgets (`models`, `cache`, `telemetry`, `working`) that shrink as
    the mode degrades — fractions sum below 1.0 so the OS keeps air;
  - an allocation ledger (`allocate`/`release`) enforces budgets with
    `EdgeMemoryError` on over-budget, duplicate, negative, or unknown
    component claims. Thread-safe via `RLock`.

## Integration

- `on_mode_change` is the hook slices 189 (model residency) and 190
  (cache tuning) will subscribe to for load-shedding.
- New module registered in the `edge` architecture layer; maps and API
  inventory regenerated; test module added to the taxonomy unit row.

## Validation notes (Execution Law rule 13)

Thresholds (256 MiB / 1024 MiB) and budget fractions are engineering
judgment, not measurements — tune per board family after on-device
profiling (slice 197).

## Verification

- `pytest tests/test_edge_memory.py tests/test_edge_platform.py` — 32 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
