# Slice 110 — Diversity metrics

**Status:** complete · **Commit:** `feat(gjallarbu-110): diversity metrics`

## Skald (inspect)
The ensemble combined votes but never measured *how different*
its members were — a council of clones gets no discount, and no
one could tell a diverse council from a redundant one.

## Rúnhild (design)
New module `hugrgate/ensemble/diversity.py` — pure, deterministic
functions over member ballots:
- Label-free (one decision's ballots): `vote_entropy` (bits),
  `disagreement_rate` (fraction of disagreeing ballot pairs),
  `winner_margin` (winner's hard-vote share minus runner-up),
  `diversity_summary` (one-call snapshot).
- Labeled (correctness / probability-for-truth histories):
  `q_statistic` (pairwise Q in [-1, 1]), `double_fault_rate`,
  `error_disagreement_rate`, `error_correlation` (Pearson).
- Degenerate inputs (zero variance, empty histories) return
  documented neutral values instead of raising.

## Eldra (code)
Stdlib only; no numpy.

## Sólrún (tests)
`tests/test_ensemble_110_diversity.py` — 16 tests green
(committed 2026-10-09; re-verified green before this commit).

## Védis (integrate)
- All eight functions exported from `hugrgate.ensemble`;
  consumed by slice 115 (correlated-error detection) and slice
  125 (diversity floor in the release gate).

## Scribe
Committed `feat(gjallarbu-110): diversity metrics` on the
campaign branch (this slice's code was written 2026-10-09 but the
commit was missed when work jumped to 111; committed now to close
the gap — the committed `__init__.py` already imported these
names, so the committed tree was import-incomplete without it).

## Artifacts
- `hugrgate/ensemble/diversity.py`
- `tests/test_ensemble_110_diversity.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_110_diversity.py -q` → 16 passed
