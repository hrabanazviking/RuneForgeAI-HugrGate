# Slice 264 — Network-flap test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_network_flap.py` (7 tests, green)

## What existed before

Slice 263 modeled the network as statically up/down per host. Real
networks **flap**: a host oscillates up/down as routes converge,
radios fade, or load balancers flap. A static model can't prove the
system rides oscillation — especially the circuit breaker's
half-open probes, which only make sense against a recovering host.

## What was built

Extended `hugrgate/chaos/network.py`:

- `NetworkSimulator.flap(host, period_s, up_fraction, clock)`:
  the host is reachable for `up_fraction` of each `period_s`
  window. `clock` is injectable (defaults to `time.monotonic`)
  so tests drive time deterministically. Validated:
  `period_s > 0`, `up_fraction ∈ [0, 1]`.
- `stop_flap(host)`, `flapping_hosts()`; `set_down` / `set_up` /
  `partition` / `set_all_up` all stop flaps on the hosts they
  touch — an explicit static state always wins over oscillation.

## The oscillation ride (deterministic, fake clock)

With a 10 s period at 50% duty and a `CircuitRegistry`
(threshold 2, reset 5 s) on the fallback chain:

1. **t=0** (up): remote serves.
2. **t=6** (down): two `BackendUnavailable`s trip the breaker
   **open**; further down-phase calls skip the remote fast
   (`"reason": "circuit_open"`, no new guard blocks).
3. **t=11** (up + timeout elapsed): half-open probe succeeds,
   breaker closes, remote serves again.

40 calls across 4 full periods: every call served, policy
thresholds untouched — flapping never weakens policy either.

## Verification

- 7 tests: exact oscillation pattern at period boundaries,
  fraction 0.0/1.0 extremes, validation, stop/override
  semantics, the full breaker ride, 40-call policy-invariance
  sweep.
- Slice-263 tests re-run green (static behavior unchanged).
- `ruff check` clean.
