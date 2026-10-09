# Slice 452 — Objective specification

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_452_objectives.py` (16 tests)

## What existed

The controller (slice 451) accepted raw `values -> float` callables as
objectives, with no way to declare direction, scale, targets, or how
several metrics combine. A weighted sum of unnormalized metrics would
be dominated by whichever metric had the largest raw scale — a silent
correctness bug in any multi-objective tuner.

## What changed

- `hugrgate/autotune/objectives.py`:
  - `ObjectiveSpec`: evaluator + `Direction` (maximize/minimize) +
    normalization `bounds` (every composite works on [0, 1] with 1.0 =
    best) + optional `target` + `meets_target()`. Non-finite results
    and raising evaluators surface as `ObjectiveError`.
  - `WeightedObjective`: scale-free weighted sum; rejects empty
    parts, duplicate ids, negative/non-finite weights, zero total.
  - `LexicographicObjective`: strict priority order — the first spec
    decides unless tied within `tolerance`; `better(a, b)` plus a
    base-2 `rank()` scalar surrogate for controllers needing one
    number.
  - `GuardedObjective`: primary fenced by guard floors; infeasible
    candidates score `-inf` so they can never beat feasible ones;
    `violations()` names the broken guards.
  - `metric_from_samples(key)`: builds an objective reading
    `values["metrics"][key]` for tuners that stash measured metrics
    into the candidate dict.

## Verification

16 new tests (validation, normalization/clamping, weighted scale
invariance, lexicographic priority and ties, guard infeasibility,
sample-metric plumbing); `ruff` and `mypy` clean.
