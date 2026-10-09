# Slice 245 — Privacy dry-run mode

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_dryrun.py` (10 tests)

## What existed

Privacy enforcement was all-or-nothing: the only way to learn
what a policy change would do was to run real decisions and
watch them get denied. Operators needed a preview.

## What changed

- New module `hugrgate/privacy_dryrun.py`:
  - `PrivacyDryRun(guard).evaluate(state, backend=..., policy=...,
    labels=...)` simulates the full outbound pipeline without
    executing it: attempt gate → local-only stripping →
    payload compile (flow policy, minimization, clearance,
    secret scan, PII scrub, redaction) or secret scan alone.
  - Returns `DryRunReport` with per-`DryRunStage`
    (allow/deny/strip/passthrough + reason), stripped fields,
    denial reason, `summary()` and `to_dict()`.
  - Never raises for policy denials; defensively detects input
    mutation (simulation must be side-effect free).

## Verification

- `pytest tests/test_privacy_dryrun.py` — 10 passed (gate
  deny, strip reporting, secret-scan deny, compiler allow/deny,
  strict local-only deny, state immutability, serialization).
- `mypy` and `ruff` clean; no import cycles.
