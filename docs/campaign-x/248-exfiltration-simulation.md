# Slice 248 — Exfiltration simulation

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_exfil.py` (8 tests)

## What existed

The fortress had never been attacked: every control was
tested in isolation, but no test asked "can data actually get
out?".

## What changed

- New module `hugrgate/privacy_exfil.py`:
  - `ExfilAttempt` — one attacker scenario (state, backend
    trust/jurisdiction, privacy class, labels, planted secret
    markers, expected verdict).
  - `ExfilSimulator` — builds (or accepts) a guard
    configuration, runs each attempt through attempt gate →
    payload compiler → marker-survival check, and reports
    **blocked** / **neutralized** / **allowed** with the
    mechanism. Never raises.
  - `default_attacks()` — 7-scenario red-team suite:
    strict→untrusted, forbidden→remote, secret smuggling,
    local-only exfil, PII in free text, jurisdiction hop, and
    a sanity allowed flow.
  - `ExfilReport` — pass/fail per scenario, `summary()`,
    serializable.
- **Real integration bug found:** the simulator initially
  didn't pass attempt labels to the payload compiler, so
  local-only stripping silently didn't run and a secret in a
  local-only field was *blocked by the secret scan* instead of
  *stripped first* (stage order is strip → scan). Fixed by
  building a per-attempt compiler with the attempt's labels.

## Verification

- `pytest tests/test_privacy_exfil.py` — 8 passed (default
  suite holds against the fortress; misconfigured guard fails
  the suite as it should; custom laundering scenario;
  serialization).
- `mypy` and `ruff` clean; no import cycles.
