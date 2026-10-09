# Slice 473 — Optimizer adversarial tests

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_473_adversarial.py` (10 tests)

## What existed

No red-team coverage: tuners were only ever tested on clean data,
and nothing proved a hostile tuner couldn't change the store.

## What changed

- `hugrgate/autotune/adversarial.py`: the red-team harness —
  - `poison_labels` / `spike_samples`: seeded, reproducible input
    corruption;
  - `label_poisoning_attack`: clean-vs-poisoned threshold tuning
    with the drift measured on *clean* held-out data;
  - `latency_spike_attack`: spiked samples must still yield a sane
    allocation (sums to budget, no starved stage);
  - `malicious_tuner_attack`: unknown/out-of-bounds/wrong-type
    proposals must leave the store byte-identical;
  - `crash_storm_attack`: all tuners crashing still leaves a
    completed, all-skipped cycle.
  - Every attack returns measurements (`AttackResult`), not just
    pass/fail.

## Honest finding (not hidden)

20% label noise on separable data is **contained** (tuner stays
silent or within 0.10 of the clean metric). **40% label noise breaks
the threshold tuner**: it chases the poisoned optimum (threshold
0.0, clean F1 falls 1.0 → 0.667, drift 0.33). The harness measures
this correctly — the test asserts the *detection*. Mitigation is
dataset provenance (slice 470: poisoned data changes the
fingerprint; pin trusted fingerprints), not tuner magic — no tuner
can distinguish poisoned labels from truth.

## Verification

10 new tests (corruption helpers exact, 20% poisoning contained,
40% poisoning detected-with-measured-drift, spike contained,
malicious tuner ×3 contained, crash storm contained,
serializable); `ruff` and `mypy` clean.
