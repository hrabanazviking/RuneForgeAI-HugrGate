# Campaign XIX — Autonomous Optimization: completion report

**Slices:** 451–475 · **Branch:** `gjallarbu/campaign-xix` · **Date:** 2026-10-09

**Mission:** allow safe automatic tuning of routing, thresholds,
calibration, and resource use. Shipped as the `hugrgate.autotune`
package: 12 tuners, 3 mode drivers, and the full safety spine
(controller, objectives, constraints, safety limits, rollback,
provenance, reproducibility, adversarial harness, benchmark,
release gate).

## Slice log

| Slice | Artifact | Tests |
|---|---|---|
| 451 | Optimization controller (`controller.py`); autotune error taxonomy in `errors.py` | 22 |
| 452 | Objective specification (`objectives.py`): weighted/lexicographic/guarded | 16 |
| 453 | Constraint specification (`constraints.py`): set + builders | 12 |
| 454 | Threshold tuner (k-fold CV + paired significance gate) | 11 |
| 455 | Confidence-gate tuner (Wilson-bound guarantees; statistical validation on controlled data) | 8 |
| 456 | Latency-budget tuner (measured vs equal-split baseline artifact) | 7 |
| 457 | Cache-policy tuner (trace-replay LRU/LFU) | 8 |
| 458 | Batch-size tuner (fitted throughput model) | 8 |
| 459 | Backend-order tuner (cost-per-success optimal; brute-force verified) | 8 |
| 460 | Ensemble-weight tuner (projected gradient ascent) | 7 |
| 461 | Calibration selector (hardened `autoselect.py`: `"none"` candidate + incumbent paired-win guard) | 12 |
| 462 | Hardware-aware tuner (tier profiles) | 9 |
| 463 | Energy-aware tuner (budget/efficiency; measured artifact) | 8 |
| 464 | Cost-aware tuner (budget/floor with 95% guarantee) | 7 |
| 465 | Privacy-constrained tuner (class ladder + epsilon budget) | 8 |
| 466 | Offline mode driver (journal + replay) | 6 |
| 467 | Shadow mode driver (mirrored verdicts) | 7 |
| 468 | Canary driver (leases + guardrail poll) | 10 |
| 469 | Rollback triggers (sustained-breach policy) | 10 |
| 470 | Optimization provenance (hash-chained records) | 9 |
| 471 | Reproducibility (run manifests + replay verification) | 6 |
| 472 | Optimizer safety limits (driver decorator) | 10 |
| 473 | Adversarial test harness | 10 |
| 474 | Autotuning benchmark (measured improvement) | 5 |
| 475 | Release gate (6 checks) + this report | 7 |

**New tests:** 231 across 25 modules, all registered in the
`docs/campaign-i/023-test-taxonomy-rebuild.md` taxonomy as unit
tests. `ruff` and `mypy` clean on all new/changed code.

## Genuine findings (not hidden)

1. **40% label noise breaks the threshold tuner** (slice 473): at
   20% noise the paired significance gate contains the damage
   (silence or ≤0.10 drift); at 40% the tuner chases the poisoned
   optimum (clean F1 1.0 → 0.667, drift 0.33). The harness measures
   this correctly. Mitigation is dataset provenance (slice 470 —
   pin trusted fingerprints), not tuner magic.
2. **`auto_select` hardening** (slice 461): the old code could never
   conclude "no calibration beats raw scores" and would dethrone an
   incumbent on noise. Both fixed backward-compatibly; all existing
   calibration tests pass unchanged.
3. **Backend order is not cheapest-first** (slice 459): the optimal
   fallthrough order sorts by cost-per-success; verified against
   brute-force permutation search on 30 randomized instances.
4. **Baseline discipline**: every tuner compares against an explicit
   measured baseline (equal-split budgets, current config simulated,
   incumbent calibrator) — no invented numbers anywhere.

## Debt / open threads

- Tuner data plumbing is operator-supplied (datasets, samples,
  scorers); no automatic telemetry-to-tuner wiring exists yet.
- `APPLIED` mode has no driver beyond the recording default —
  fleet-wide application is deliberately unimplemented pending
  canary evidence policy.
- The release gate's reproducibility check uses a small synthetic
  dataset; a production gate should pin real dataset fingerprints.

## Verification

- Full autotune test selection green (see slice 475 evidence).
- `ruff check` clean on `hugrgate/autotune`, `hugrgate/errors.py`,
  `hugrgate/calibration/autoselect.py`, and all new tests.
- `mypy` clean on all new/changed modules.
- No benchmark measurement artifacts committed (`benchmarks/*.json`
  untouched).
- README.md untouched (prose forbidden); CHANGELOG gained an
  additive Campaign XIX section.
