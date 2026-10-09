# Slice 114 — Minority-report preservation

**Status:** complete · **Commit:** `feat(gjallarbu-114): minority-report preservation`

## Skald (inspect)
`metadata["ensemble"]["minority_report"]` has been populated since
slice 101, but there was no first-class API to *read* it, render it
for humans, or *verify* it was complete — preservation was asserted,
not auditable.

## Rúnhild (design)
Minority-report API in `hugrgate/ensemble/disagreement.py`:
- `MinorityReport` dataclass (backend, value, probability, weight)
  with `to_text()` human rendering.
- `minority_report(result)` extractor — always returns a list; the
  key exists on every ensemble result (empty when unanimous), so
  dissent can never be silently dropped.
- `audit_minority_report(result, votes)` — returns problems, empty
  when faithful: catches a dissenting ballot missing from the
  report, a phantom report entry with no ballot, and ballot/report
  value mismatches. Abstentions (no winner) are skipped.

Process note: the `MinorityReport` dataclass rode along unexported
in the slice-112 file commit (an over-broad restore); it was never
in `__all__` nor exported until this slice. This commit exports it
and adds the genuinely new `audit_minority_report`.

## Eldra (code)
Real extraction/audit logic, no stubs.

## Sólrún (tests)
`tests/test_ensemble_114_minority.py` — 10 tests green:
success (extraction with exact fields, unanimous → empty-but-present,
report key on all four voting strategies, faithful audit passes),
failure-detection (missing dissenter, phantom entry, value
mismatch — each caught with a naming message),
boundary (abstention audit is a no-op, skipped votes handled,
report extraction on escalation-abstained results).
Ensemble suite: 180 passed; mypy clean.

## Védis (integrate)
- `MinorityReport`, `minority_report`, `audit_minority_report`
  exported from `hugrgate.ensemble`; the audit closes the loop with
  slice 101's `finalize_result` contract.

## Scribe
Committed `feat(gjallarbu-114): minority-report preservation`;
branch `gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/disagreement.py` (`audit_minority_report`,
  exports)
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_114_minority.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_10*.py tests/test_ensemble_11*.py -q` → 180 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
