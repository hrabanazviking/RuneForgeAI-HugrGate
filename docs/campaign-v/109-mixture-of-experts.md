# Slice 109 — Mixture-of-experts router

**Status:** complete · **Commit:** `feat(gjallarbu-109): mixture-of-experts router`

## Skald (inspect)
Every strategy so far asked the same members about every input.
Nothing routed by input region — the mixture-of-experts pattern.

## Rúnhild (design)
New module `hugrgate/ensemble/moe.py`:
- `ExpertRouter(members, feature_names, top_k=None)` — numeric state
  features (missing/non-numeric → 0.0, documented); `fit(states,
  votes_per_sample, labels, spec)` trains a softmax gating network
  with batch GD from zero init (deterministic). Targets are *soft*:
  uniform over the experts that voted the true label (uniform over
  all when none did). `route(state, candidates)` and
  `route_topk(state, k, candidates)` (renormalized top-k).
- `moe_combine` registered as `"moe"`: needs a fitted router in
  `ctx.fitted` **and** the input state — so `StrategyContext` gains
  an optional `state` field (backward compatible; `Ensemble.evaluate`
  now wires it in), and `top_k` is overridable via
  `strategy_options`. Combines routed experts by gate-weighted
  distribution average.

## Eldra (code)
Real gating math in pure Python; discrete specs only.

## Sólrún (tests)
`tests/test_ensemble_109_moe.py` — 12 tests green. Centerpiece: on
two-region data (expert_a right for x<0.5, expert_b for x≥0.5) the
router gates x=0.1 → expert_a @0.92 and x=0.9 → expert_b @0.94, and
the MoE decision follows the routed expert per region. Also:
decisive top-1 routing, feature-extraction edge cases, fit
determinism, combine-needs-router/state failures, router validation,
route-before-fit, candidates restriction, top_k option override.
Ensemble suite: 122 passed; mypy clean.

## Védis (integrate)
- `"moe"` in the registry; `ExpertRouter`, `moe_combine` exported;
  `StrategyContext.state` added (additive, no existing caller
  affected).

## Scribe
Committed `feat(gjallarbu-109): mixture-of-experts router`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/moe.py`
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/base.py`,
  `hugrgate/ensemble/__init__.py`
- `tests/test_ensemble_109_moe.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py tests/test_ensemble_104_weighted_voting.py tests/test_ensemble_105_confidence_voting.py tests/test_ensemble_106_bma.py tests/test_ensemble_107_stacking.py tests/test_ensemble_108_blending.py tests/test_ensemble_109_moe.py -q` → 122 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
