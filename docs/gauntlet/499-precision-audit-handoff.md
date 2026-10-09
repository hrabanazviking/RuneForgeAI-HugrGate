# Slice 499 — Independent precision audit handoff

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_499_handoff.py` (8 tests)

## The package

An independent auditor gets two artifacts:

1. **`docs/gauntlet/499-audit-handoff.json`** (machine-readable) —
   7 claims (CAL-01, PERF-01, DOC-01, LIC-01, RC-01, API-01,
   FRZ-01), each with the exact reproduce command, the evidence
   files, and the expected result. Commands run from the repo
   root with the project venv.
2. **`tools/precision_handoff_check.py`** — verifies the package
   itself is complete and actionable: valid schema, every
   evidence file exists, every reproduce command references an
   existing script/test file. (Running the reproductions is the
   auditor's job; the checker proves the handoff isn't pointing
   at air.)

## Claims at a glance

| ID | Claim | Reproduce |
|---|---|---|
| CAL-01 | ECE agrees with ground truth (perfect 0.0092, monotone) | `pytest tests/test_gauntlet_494_calibration_audit.py -q` |
| PERF-01 | Benchmark deterministic, CV 0.068 | `pytest tests/test_gauntlet_495_repro.py -q` |
| DOC-01 | Doc snippets executable: 3 pass, 4 skip, 0 fail | `python tools/docs_exec_audit.py …` |
| LIC-01 | Runtime closure license-clean (Apache-2.0 + MIT) | `python tools/license_audit.py` |
| RC-01 | sdist+wheel build & verify 5/5 | `python tools/rc_build.py …` |
| API-01 | Public API matches 1.0 baseline (422 modules, 2563 names) | `pytest tests/test_gauntlet_486_api_audit.py -q` |
| FRZ-01 | Feature freeze enforced | `pytest tests/test_gauntlet_476_freeze.py -q` |

## Verification

`precision_handoff_check.py` → **handoff complete, exit 0**.
8 checker unit tests green; `ruff`/`mypy` clean.
