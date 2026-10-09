# Slice 267 — Dependency failure matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_dependency_matrix.py` (6 tests, green)

## What existed before

Optional dependencies (`numpy`, `scikit-learn`) were handled with
`try/except ImportError → None` plus `_require_*()` guards raising
`BackendError` — but nothing *simulated* their absence, and one
subsystem failure was load-bearing: `HugrGate.decide()` called
`self.provenance.append(...)` unguarded, so a failing provenance
store (full disk, corruption) **failed the entire decision** even
though the backend had answered fine. Observability was holding
decisions hostage.

## Attack (Yrsa Law 11)

Simulated `provenance.append` raising `OSError`: confirmed
`decide()` propagated it and the decision was lost. Fixed.

## What was built

Extended `hugrgate/chaos/experiments.py` with the dependency matrix:

- **`DependencyScenario`** (name, description, `break_it() →
  restore()`, `check()` raising on non-graceful degradation).
  `restore` runs even when `check` raises.
- **`DependencyMatrix`** — `add`, `scenarios`, `run_all()` returning
  a JSON-serializable report; never aborts, records per-scenario
  survival.
- **`builtin_dependency_matrix()`** — three shipped scenarios
  simulating absent optional deps via module-attribute patching:
  `ml-numpy-missing`, `ml-sklearn-missing`,
  `embedding-numpy-missing`. Each asserts the failure surfaces as
  `BackendError` **with an install hint** — never a leaked
  `ImportError`/`AttributeError`.
- **`dependency_failure_matrix()`** — runs the builtins, returns
  the report.

Hardening in `hugrgate/core.py`: the provenance append is now
best-effort — on failure it logs a warning and the decision is
kept. Provenance is observability, not the decision.

## Verification

- 6 tests: all 3 builtin scenarios survive; patched modules are
  restored afterward; matrix never aborts (break/check/restore
  failures each recorded); restore-failure marks non-survival;
  bad-scenario rejection; and the slice's proof —
  `provenance-store-down` (added to the matrix in-test):
  `decide()` returns the accepted result while `append` raises,
  with a non-vacuous assertion that `append` was attempted.
- `test_errors.py` re-run green — including the raise-site gate
  (the filesystem simulator's deliberate `OSError` uses the
  attribute form, matching the `cluster/chaos.py`
  `httpx.ConnectError` precedent for simulated failures).
- `ruff check` clean.
