# Slice 034 — Numeric uncertainty intervals

## What existed before
- `DecisionSpec(type="numeric")`: a point value in `[minimum, maximum]` —
  no uncertainty, no intervals, no confidence.

## What changed
- **`hugrgate/contracts/uncertainty.py`** (new, kind `"numeric-interval"`):
  - `UncertainValue`: frozen `(estimate, lower, upper, confidence)` with
    `lower ≤ estimate ≤ upper` and `confidence ∈ (0, 1]` (1.0 = a certain
    point); dict round-trip; `point(x)` constructor.
  - `NumericIntervalContract`: estimate range `[minimum, maximum)` plus
    optional `max_width` and `min_confidence` guards. `validate_value`
    accepts plain numbers (coerced to zero-width certain intervals),
    mappings, and `UncertainValue`s — point estimates stay first-class.
  - Pure interval algebra: `width`, `contains` (inclusive), `covers`,
    `intersect` (None when disjoint; estimate clipped into overlap,
    conservative confidence), `widen` (scales half-widths around the
    estimate), `coerce`.
- **`hugrgate/contracts/__init__.py`**: lazy `uncertainty` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Confidence bound is `(0, 1]`, not `(0, 1)`: tests caught that a
  degenerate certain point (confidence 1.0) is legitimate and must
  validate — the initial exclusive bound was wrong and was fixed.
- Interval *and* estimate must both sit inside `[minimum, maximum]`; an
  interval may not poke outside the allowed range even if its estimate is
  inside.

## Tests
- `tests/test_contracts_034.py`: 27 tests — construction guards, coercion
  paths, containment/covering, intersection (overlap/disjoint/touching),
  widening, `max_width`/`min_confidence` enforcement, round-trips,
  bool-is-not-numeric.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/uncertainty.py`, `tests/test_contracts_034.py`.
