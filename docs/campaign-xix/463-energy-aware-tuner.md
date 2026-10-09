# Slice 463 — Energy-aware tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_463_energy.py` (8 tests)

## What existed

No energy dimension existed in the optimizer: quality was maximized
with no notion of joules-per-decision cost.

## What changed

- `hugrgate/autotune/tuners/energy.py`: `EnergyAwareTuner` chooses
  among discrete operating choices from **measured** per-decision
  energy (joules) and quality samples:
  - `budget` mode: maximize mean quality subject to
    mean + 1 SE <= budget (conservative feasibility — no gambling on
    noise);
  - `efficiency` mode: maximize quality per joule;
  - an over-budget incumbent scores **−inf** (a violation to escape,
    not a baseline to beat);
  - choices with < 20 samples are excluded (a mean over three
    samples is not a measurement).
  - The proposal evidence is the reproducible measurement artifact:
    per-choice measured means/SEs/sample counts, the explicit
    baseline (current choice on the same samples), and the tuned
    choice — re-derivable by re-running with the same seed. No
    invented numbers.

## Verification

8 new tests (budget mode picks best quality under budget,
conservative feasibility at the boundary, efficiency mode,
silence when optimal or nothing feasible, determinism, spec
validation, end-to-end offline); `ruff` and `mypy` clean.
