# Slice 025 — Foundation release gate

**Date:** 2026-10-09 · **Tests:** `tests/test_release_gate.py` (6 tests)

## The gate

The campaign's Definition of Done as executable checks, run on every
suite invocation (marked `gate`):

1. **Version truth**: `hugrgate.__version__` equals the pyproject
   declared version (0.1.0).
2. **Changelog currency**: `CHANGELOG.md` carries the
   "Gjallarbrú Campaign I" Unreleased section recording all 25
   slices and the 533-test figure.
3. **Evidence per slice**: all 25 slice docs present in
   `docs/campaign-i/` and non-trivial (>400 chars each).
4. **Completion report**: `CAMPAIGN-I-COMPLETION-REPORT.md` exists
   and states the final count.
5. **Benchmark smoke**: the hardened core still benchmarks —
   100-item rules triage scores ≥0.9 accuracy, no crashes.

## Cross-campaign items (§4)

- **Full suite**: 533 tests green; mypy clean (44 files); ruff
  clean; coverage 90% total.
- **Regression review**: `git log` reviewed slice by slice; the only
  behavioral surprises found during the campaign were converted
  into pinned tests (ladder SpecError propagation, `recent(0)`,
  daemon stop stranding).
- **New dependencies**: `ruff>=0.8` + `coverage>=7.0` (new `lint`
  extra, dev-only); `mypy` was already declared via `typecheck`.
  No runtime dependency changes.
- **README claims**: verified against reality — two claims are now
  stale (322-test count, dated implementation notes). README prose
  is Volmarr's and was not touched; the corrections are recorded
  in the completion report for his review.
- **Unresolved debt**: recorded in the completion report.

## Verification

6 gate tests green; full suite green; push verified with
`git ls-remote`.
