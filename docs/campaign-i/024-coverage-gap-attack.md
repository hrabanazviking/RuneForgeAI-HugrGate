# Slice 024 — Coverage gap attack

**Date:** 2026-10-09 · **Tests:** `tests/test_coverage_attack.py` (25 tests)

## Method

Ran coverage over the suite (full suite: 90% total) and attacked the
thinnest genuinely-unit-testable modules instead of chasing the
number: `validate_result`'s numeric/multilabel/distribution-key
branches, spec validation branches, `TimeoutBackend`'s delegate
surface, `ModelManifest`/`ModelStore` failure paths, and core
`decide`/`close` branches.

## Measured improvement (unit+integration subset)

| Module | Before | After |
|---|---|---|
| `validation.py` | 83% | **100%** |
| `spec.py` | 88% | 95% |
| `core.py` | 82% | 91% |
| `timeout.py` | 85% | 98% |
| `models.py` | 88% | 98% |

Full suite: 90% total. Remaining thin spots are dominated by
optional-dependency backends (`llm.py` 74%, `nli.py` 73% — heavy
deps absent in CI) and the service surface already exercised by the
slow tests.

## Verification

25 new tests green; full suite 527 passed; ruff and mypy gates
clean. (One self-inflicted failure during the slice —
`import tests.conftest` tripped the dependency rule — fixed via
importlib loading.)
