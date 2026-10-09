# Slice 116 — Backend reliability weighting

**Status:** complete · **Commit:** `feat(gjallarbu-116): reliability weighting`

## Skald (inspect)
Weights were static operator assignments — nothing converted a
member's *track record* into weight. A member that is right 90% of
the time counted the same as one right 40% of the time unless a
human intervened.

## Rúnhild (design)
New module `hugrgate/ensemble/reliability.py`:
- `ReliabilityTracker(members, smoothing=1.0)` — `observe(member,
  correct)` records labeled outcomes; `reliability()` is the
  Laplace-smoothed accuracy `(s+α)/(n+2α)` (new members start at 0.5:
  no condemnation without evidence); `weights()` normalizes
  reliability × penalty to sum to 1, ready for
  `Ensemble(weights=...)`.
- `penalize(member, factor)` / `clear_penalties()` — manual trust
  adjustments in [0, 1].
- `apply_correlation_report(report, factor=0.5)` — the slice-115
  wiring: in each correlated-error clique the most reliable member
  keeps full weight, the rest are penalized, so duplicated minds
  stop buying duplicate influence.

## Eldra (code)
Real evidence-to-weight math; misconfiguration raises
`PolicyError`.

## Sólrún (tests)
`tests/test_ensemble_116_reliability.py` — 9 tests green:
success (Laplace 0.5 start, exact smoothed math 10/12, weights feed
weighted voting end-to-end with the reliable member winning the
tie, correlation penalties demote the duplicate, `to_dict`),
failure (all constructor/observer validations, zero-total-weight
guard),
boundary (tunable smoothing strength).
Ensemble suite spot-checked; mypy clean.

## Védis (integrate)
- `ReliabilityTracker` exported; documented usage pattern
  `Ensemble(members, strategy="weighted",
  weights=tracker.weights())`; consumes slice 115's reports.

## Scribe
Committed `feat(gjallarbu-116): reliability weighting`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/reliability.py`
- `hugrgate/ensemble/__init__.py` (export)
- `tests/test_ensemble_116_reliability.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_116_reliability.py -q` → 9 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
