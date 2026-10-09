# Slice 140 — Cold-start routing

**Status:** complete. **Tests:** `tests/test_adaptive_coldstart.py` — 10 tests green.

## What existed before

New backends (or new domains/contracts) had no history, and the bandit
started every arm at zero — "no history" meant either "never tried" or
"systematically under-explored when rewards are positive".

## What was built

`hugrgate/adaptive/coldstart.py` — `ColdStartRouting`:

- **Shrinkage priors**: `(n·own_mean + k·fleet_mean)/(n + k)` — at n=0 the
  fleet mean *is* the estimate; evidence takes over as it accumulates.
  Fleet mean is the honest fleet average (0.5 neutral when nothing exists
  anywhere).
- `seed_bandit`: translates shrunk priors into bandit `seed_prior` calls so
  LinUCB explores newcomers from "average", not zero.
- `recommend`: arms below `maiden_voyages` observations compete among
  themselves by shrunk mean — newcomers get their first real trials instead
  of starving behind incumbents.
- `prior_report` / `cold_arms`: every shrinkage auditable.

## Integration

- Consumes slice-137 profiles; seeds slice-130 bandits; `SpecError` on bad
  constructor args.

## Verification

- `pytest tests/test_adaptive_coldstart.py` — 10/10 green: shrinkage math
  (thin history pulled toward fleet, veteran barely moves), fleet/neutral
  priors, maiden-voyage prioritization and graduation, bandit seeding gives
  the newcomer nonzero expectation, auditable reports.
- `mypy hugrgate/adaptive` — clean.
