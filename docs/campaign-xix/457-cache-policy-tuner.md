# Slice 457 — Cache-policy tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_457_cache.py` (8 tests)

## What existed

`DecisionCache` (slice-era `hugrgate/cache.py`) shipped with
hand-picked TTL/size and a fixed LRU discipline. Nothing measured
whether those settings fit the actual access pattern.

## What changed

- `hugrgate/autotune/tuners/cache.py`: `CachePolicyTuner` replays a
  recorded (key, timestamp, miss_cost) trace through a simulator over
  a grid of (ttl × max_size × eviction) candidates and proposes the
  minimum-total-miss-cost configuration:
  - `simulate_trace`: insert/access/expiry/eviction with LRU and LFU
    disciplines (LFU breaks frequency ties by recency);
  - ttl on a linear grid inside the param bounds, max_size on a
    geometric ladder clipped to the bounds (falls back to bound
    endpoints), eviction over the param's declared choices;
  - the current config is simulated as the baseline; the winner must
    beat it by `min_delta` (costs negated so higher is better).
  - The simulator's limits are documented in the evidence: it does
    not model policy-fingerprint namespacing.

## Verification

8 new tests (simulator hits/expiry, LRU-vs-LFU divergence with
hand-verified counts, tuner beats baseline on a hot-key trace with
72 candidates evaluated, determinism, silence when already optimal,
spec validation, type rejection, end-to-end offline); `ruff` and
`mypy` clean.
