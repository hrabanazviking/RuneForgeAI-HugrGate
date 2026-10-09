# Slice 477 — Fresh-clone install gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_477_install.py` (8 tests)

## What existed

No install path was ever exercised from a clean state: the venv in
the main repo dir is warm, and nothing proved `pip install .`
produces a working distribution.

## What changed

- `tools/fresh_clone_install.sh` (new, executable): clones the repo
  (default: origin/HEAD) into a fresh temp dir, builds a brand-new
  venv, `pip install .` with no cache and no extras, runs the smoke
  probe, checks the `hugrgate` console entry point, and cleans up
  unless `KEEP_CLONE=1`.
- `tools/install_smoke.py` (new): runs *inside* the fresh env —
  asserts the import came from site-packages (not a checkout),
  registers a minimal deterministic backend, runs `gate.decide`
  end to end on a categorical spec, and verifies the CLI entry
  point resolves.

## Verification

`pytest tests/test_gauntlet_477_install.py` green (script syntax via
`bash -n`, probe compile + real decide() path, entry-point
resolution, `hugrgate --help`); `ruff` clean. The full
clone+install run is a manual release step, not a unit test —
running it is recorded in the 1.0 release decision (slice 500).
