# Slice 147 — Adaptive-route explanations

**Status:** complete. **Tests:** `tests/test_adaptive_explanations.py` — 11 tests green.

## What existed before

Routing decisions were opaque — no "why this arm?" for review, incidents,
or regulated settings. (Campaign III's `routing/explain.py` lives on another
branch; this is the adaptive layer's own explainer, built on bandit
internals and competence data.)

## What was built

`hugrgate/adaptive/explanations.py` — `AdaptiveRouteExplainer`:

- `explain(chosen, scores, features, feature_weights, objective_note)` →
  `RouteExplanation`: winner, runner-up, margin, top-K feature contributions
  (`weight × value`, ranked by |impact|), competence note (attempts, success
  rate, Wilson lower bound, rank — or honest "no history"), objective note,
  and a narrative `text` where every sentence cites a number in the
  explanation. Unknowns stated as unknowns; causes never invented.
- `explain_candidates(candidates, score_fn)`: convenience scoring +
  deterministic tie-break (smallest arm name).

## Integration

- Consumes slice-132 candidates/scores, slice-137 profiles, slice-130
  bandit thetas as feature weights; `SpecError` on unscored choices.

## Verification

- `pytest tests/test_adaptive_explanations.py` — 11/11 green: winner/
  runner-up/margin, single-candidate case, contribution ranking math,
  competence notes (with and without history), objective notes in text,
  convenience path, serialization shape.
- `mypy hugrgate/adaptive` — clean.
