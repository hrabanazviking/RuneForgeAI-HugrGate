# Slice 015 — Provenance integrity

**Date:** 2026-10-09 · **Tests:** `tests/test_provenance_integrity.py` (10 tests)

## Real bugs found and fixed

| Bug | Impact |
|---|---|
| "Append-only" was a docstring: records were stored and returned by reference, so any holder could rewrite history | silent history mutation |
| `recent(0)` returned the **entire** history (`[-0:] == [0:]`) | full-history leak on a boundary input |
| No tamper detection on the stored list | edits invisible |

## Changes (`hugrgate/provenance.py`)

- `DecisionRecord` gains `prev_hash` / `record_hash` (defaults → old
  constructions still work).
- `ProvenanceStore.append`: `TypeError` for non-records; deep-copies
  the record in; assigns `prev_hash` = tip hash and `record_hash` =
  SHA-256 over the canonical record + previous hash.
- `by_hash` / `recent` return deep copies (read path cannot mutate
  history either).
- `recent(n)`: `n < 0` → `ValueError`; `n == 0` → `[]`.
- `verify_chain() -> bool`: recomputes every link; detects edits and
  reordering of the stored list.

## Verification

10 new tests green (incl. direct attacks on the stored list and
held-reference mutation); full suite 457 passed; mypy clean.
