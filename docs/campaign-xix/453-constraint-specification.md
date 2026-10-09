# Slice 453 — Constraint specification

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_453_constraints.py` (12 tests)

## What existed

The controller accepted raw constraint callables, but there was no
vocabulary for declaring the fences operators actually need:
operating envelopes, conditional rules, mutual exclusion, and budget
caps all had to be hand-rolled per deployment.

## What changed

- `hugrgate/autotune/constraints.py`:
  - `ConstraintSpec` (id + predicate + message + severity) with
    `check()` returning a structured `Violation`, and `as_callable()`
    for controller registration. A raising predicate becomes a
    `ConstraintViolation`, never a crash.
  - `ConstraintSet`: ordered, id-deduplicated; `validate()` raises on
    the first breach, `validate_all()` collects every breach,
    `as_callables()` plugs into the controller.
  - Builders: `within_bounds` (soft envelope inside the store's hard
    bounds), `requires` (arbitrary predicate), `implies` (conditional:
    if A then B in set), `mutual_exclusion` (at most one active),
    `sum_leq` (budget cap), `change_within` (per-cycle delta cap vs a
    baseline).
  - Missing parameters fail closed; violation messages name the rule,
    never secret values (privacy).

## Verification

12 new tests (each builder, exception isolation, duplicate ids,
first-breach vs collect-all, end-to-end rejection through the
controller); `ruff` and `mypy` clean.
