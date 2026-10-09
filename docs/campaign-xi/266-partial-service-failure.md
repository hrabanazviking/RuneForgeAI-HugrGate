# Slice 266 — Partial-service failure

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_partial_service.py` (9 tests, green)

## What existed before

The chaos framework (slice 251) defined the experiment discipline
and the fault libraries (252–265) provided the injectors — but
there was no *composed* experiment proving the headline claim:
"the service keeps serving when part of it dies." Faults existed;
the failure story didn't.

## What was built

`hugrgate/chaos/experiments.py` — the standard experiment library:

- **`ServiceUnderTest`** — a `FallbackChain` over named backends,
  some wrapped in `FaultyBackend`. `inject_crash` / `recover` /
  `crashed_names` / `is_healthy`, plus `safe_default` passthrough.
  Crucially, `decide()` **mirrors the core decision path**
  (`HugrGate.decide`): result validation + the policy gate apply,
  so below-threshold results abstain instead of being served —
  the harness can't prove a weaker property than production.
- **`partial_service_failure_experiment`** — two modes:
  - one-at-a-time: each victim becomes a fault (inject crashes,
    verify asserts the victim *is crashed* and the service still
    serves an accepted result, rollback heals);
  - `simultaneous=True`: one fault crashes everything at once;
    verify asserts the service **fails cleanly** (abstains)
    instead of serving garbage.
- Steady-state probes: `service-serves` before/after,
  `policy-intact` throughout; blast radius locked to `chaos-lab`.

## Falsifiability (the point of the slice)

- One victim of three crashes → serves via survivors: **holds**.
- Two victims → serves via the last survivor: **holds**.
- All victims at once (abstain policy) → clean `Abstention`:
  **holds**.
- All victims at once with `safe_default` → serves the default
  *by design* → the "fails cleanly by abstaining" hypothesis is
  **falsified**, and the report says exactly that.
- Unhealthy baseline (nothing can serve pre-fault) → steady-state
  failure, not a quiet pass.
- Mid-experiment policy mutation → caught by the policy probe.

## Verification

- 9 tests: harness validation, builder validation, both modes,
  both falsifications, unhealthy baseline, blast-radius guard,
  policy-mutation detection. Reports JSON-serializable.
- `ruff check` clean; no import cycles.
