# Slice 136 — Multi-objective routing

**Status:** complete. **Tests:** `tests/test_adaptive_multiobjective.py` — 14 tests green.

## What existed before

Slices 132–135 each optimized one trade-off; nothing composed them.

## What was built

`hugrgate/adaptive/multiobjective.py`:

- `MultiObjectiveRouter`: composes `(objective, weight)` pairs in two modes —
  `weighted_sum` (`Σ wᵢ·scoreᵢ`; the weights *are* the value judgment) and
  `lexicographic` (priority-ordered; first distinguishing objective decides —
  for "never trade X for Y" requirements weights can't express).
  Lexicographic mode has no scalar `score()` (raises `SpecError` directing to
  `rank()`) — honest about not being a total order.
- `dominates` / `pareto_frontier`: the non-dominated set over
  (quality↑, cost↓, latency↓, energy↓) — the honest "what are my real
  options?" before any scalarization picks a winner.
- `explain_weights()`: the value judgments made auditable.

## Integration

- Composes slice-132/133/134/135 objectives via the shared `RouteObjective`
  interface; `SpecError` on unknown modes, empty lists, negative/all-zero
  weights, non-objectives.

## Verification

- `pytest tests/test_adaptive_multiobjective.py` — 14/14 green: weighted-sum
  ranking and weight linearity, lexicographic quality-first and tie
  fall-through, Pareto frontier excludes the dominated arm and keeps input
  order, `dominates` semantics (incl. not self-dominating), auditable weights.
- `mypy hugrgate/adaptive` — clean.
