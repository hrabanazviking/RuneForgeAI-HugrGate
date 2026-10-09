# Slice 049 — Contract fuzzing

## What existed before
- 853 tests, all hand-written examples — strong on the cases we thought
  of, blind to the ones we didn't.

## What changed
- **`hugrgate/contracts/fuzz.py`** (new): seeded property fuzzer.
  - `random_contract(rng, kind=None)` — generators for six kinds
    (nested-categorical incl. real child contracts, ordinal with sorted
    anchors, numeric-interval, multilabel, cost-sensitive,
    distribution with `min_mass` constraints).
  - `random_valid_value` / `random_invalid_value` /
    `random_valid_distribution` (constraint-aware: repairs mass to
    satisfy `min_mass` with a margin).
  - `fuzz(seed, cases_per_kind, values_per_case)` — checks five
    invariant families per case: dict round-trip, canonical-hash
    stability, non-empty `describe()`, `validate_value` soundness on
    in-space values, `validate_distribution` on fitted distributions.
    Invalid values are advisory (warnings, not failures — the generator
    is heuristic, the contract is truth).
  - `FuzzReport(seed, cases, invariants, failures, warnings)` with
    `passed` and `describe()`; fully deterministic per seed, so a
    failure is a reproduction recipe.
- Five seeds × 40 cases × 6 kinds (~1,200 cases, ~15k invariant checks):
  **zero failures** — the engine holds.
- Writing the generators caught four real construction rules the hard
  way (`max_count=0` = unbounded, children must be contract instances,
  `anchors=None` rejected, strictly-increasing anchors) — the fuzzer
  now encodes them all.

## Design decisions
- Sampler bugs surface loudly (not swallowed): during development the
  fuzzer crashed on my own mistakes, which is exactly the behavior you
  want from a bug-hunting tool.
- Invalid-value acceptance is a warning, not a failure — keeps the
  fuzzer sound while still surfacing suspicious leniency.

## Tests
- `tests/test_contracts_049.py`: 15 tests — fixed-seed regression net
  (5 seeds), kind coverage, determinism, sampler soundness,
  distribution fitting, invalid-value rejection rate, report API,
  config guards.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/fuzz.py`, `tests/test_contracts_049.py`.
