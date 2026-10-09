# Slice 177 — Raspberry Pi baseline

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_platform.py` (19 tests, green — 7 new)

## What existed before

Slice 176 gave HugrGate host introspection but no notion of *which*
board it runs on — memory modes, cache tuning, and benchmarks (slices
178, 189–190, 196–198) need calibrated per-board anchors.

## What was built

Extended `hugrgate/edge/platform.py`:

- **`detect_pi_board(cpuinfo_text=None, model_text=None)`** — parses
  `/proc/cpuinfo` (`Model`/`Revision` lines) and the device-tree model
  file to return a `PiBoard(model, revision, ram_mb, detected_live)`,
  or `None` on non-Pi hosts (never raises). Key parsing is exact-match
  (a `startswith` bug that grabbed per-CPU `model name` lines instead
  of the board `Model` line was found by tests and fixed — pinned by
  `test_detect_pi4_from_cpuinfo`). Unknown revisions fall back to the
  smallest published RAM figure for the matching board family.
- **`PiBoard` / `EdgeBaseline`** — frozen, JSON-serializable records.
- **`PI_BASELINES`** — conservative baselines for Pi 5, Pi 4B, Pi 3B+,
  Zero 2 W (CPU, RAM, cache-entry and resident-model recommendations,
  power budgets, board-specific caveats).
- **`pi_baseline(board | label)`** — resolves a board or free-text
  label to a baseline; raises `ValueError` listing known models for
  unknown labels rather than guessing (guessing would silently
  miscalibrate downstream subsystems).

## Integration

- Board RAM/CPU figures feed slices 178 (low-RAM mode), 189 (model
  residency), 190 (cache tuning) via `pi_baseline()`.
- No new layer entries needed (same module); regenerated
  `architecture-map.md` — byte-identical, confirming determinism.

## Validation notes (Execution Law rule 13)

Board specs are published manufacturer figures, not measurements.
`detected_live=False` marks fixture-derived boards. Power budgets and
thermal caveats in baselines are guidance until measured on-device.

## Verification

- `pytest tests/test_edge_platform.py` — 19 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
- `pytest tests/test_taxonomy.py tests/test_arch_map.py tests/test_api_inventory.py` — 18 passed
