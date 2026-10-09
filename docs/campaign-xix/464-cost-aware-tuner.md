# Slice 464 — Cost-aware tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_464_cost.py` (7 tests)

## What existed

The optimizer had no money dimension: the energy tuner (463) handled
joules, but per-decision dollar cost was invisible.

## What changed

- `hugrgate/autotune/tuners/cost.py`: `CostAwareTuner` chooses among
  priced choices from measured per-decision cost (dollars) and
  quality samples:
  - `budget` mode: maximize mean quality with mean + 1 SE <= budget;
  - `floor` mode: minimize mean cost subject to the statistical
    guarantee mean − 1.96·SE >= quality_floor (~95% confidence);
  - infeasible incumbents score −inf (violations to escape);
  - evidence carries the full measured comparison.

## Verification

7 new tests (budget mode, floor mode with the guarantee checked on
the measured numbers, silence when optimal/infeasible,
determinism, spec validation, end-to-end offline); `ruff` and `mypy`
clean.
