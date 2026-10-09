# Slice 106 — Bayesian model averaging adapter

**Status:** complete · **Commit:** `feat(gjallarbu-106): Bayesian model averaging`

## Skald (inspect)
No Bayesian combination existed. The voting strategies (102-105)
use fixed or self-reported weights; none maintain *posterior model
probabilities* updated from labeled feedback.

## Rúnhild (design)
New module `hugrgate/ensemble/averaging.py`:
- `BayesianModelAverager(members, priors=None)` — operator priors
  (uniform default), `observe(member, log_likelihood)` accumulating
  log-evidence, `observe_outcome(member, distribution, true_label)`
  scoring one labeled outcome via `predictive_log_likelihood`
  (`log P(truth)`, floored at `log(1e-12)` — harsh but finite, never
  `-inf`), `posterior_weights()` = numerically-stable softmax over
  `log(prior) + log_evidence`. Members with no observations fall back
  to their prior.
- `bma_combine` registered as strategy `"bma"`: posterior-weighted
  average of (completed) member distributions. The averager rides in
  `StrategyContext.fitted`; without one the combiner refuses with a
  helpful error instead of guessing.
- **Bug found by tests:** posterior mass leaked to averager members
  that cast no ballot, so the average stopped summing to 1
  (uncertainty 1.05!). Fixed: the posterior is renormalized over the
  members that actually voted.

`Ensemble` gains the fitted-model channel: constructor kwarg
`fitted=` and fluent `attach()`; `evaluate` passes it into
`StrategyContext`. (Also repaired an edit collision that had stranded
the weight-normalization block after `attach`'s `return` — caught by
the 101/104/105 regression tests + mypy.)

`_complete_distribution` promoted from `voting.py` to public
`base.complete_distribution` so `averaging.py` doesn't reach into
voting's privates.

## Eldra (code)
Real Bayesian update math, no stubs. All validation raises
`PolicyError` (config) or `BackendError` (degenerate combine).

## Sólrún (tests)
`tests/test_ensemble_106_bma.py` — 19 tests green:
success (prior fallback, exact posterior math 0.45/0.65,
evidence accumulates 10/10 → posterior > 0.99 for the better member,
custom priors, `observe_outcome` returns the ll, ll flooring,
bma==soft under uniform posterior, evidence tilts the combine,
end-to-end `Ensemble(strategy="bma")` via `attach()` and via
constructor kwarg, `to_dict`),
failure (no fitted / wrong fitted type → `BackendError`, unknown
member, bad priors ×5, non-finite ll, numeric spec),
boundary (single member posterior 1.0, silent member gets no mass —
the test that caught the renormalization bug).
Ensemble suite: 86 passed; mypy clean.

## Védis (integrate)
- `"bma"` in the strategy registry; `BayesianModelAverager`,
  `bma_combine`, `predictive_log_likelihood`, `complete_distribution`
  exported from `hugrgate.ensemble`.

## Scribe
Committed `feat(gjallarbu-106): Bayesian model averaging`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/averaging.py`
- `hugrgate/ensemble/api.py` (`fitted`/`attach`), `base.py`
  (`complete_distribution`), `__init__.py` (exports)
- `tests/test_ensemble_106_bma.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py tests/test_ensemble_104_weighted_voting.py tests/test_ensemble_105_confidence_voting.py tests/test_ensemble_106_bma.py -q` → 86 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
