# Slice 119 — Ensemble provenance

**Status:** complete · **Commit:** `feat(gjallarbu-119): ensemble provenance`

## Skald (inspect)
Ensemble results carry rich metadata, but `DecisionRecord`
dropped it — `from_decision` kept only state keys. Council rulings
left no auditable trace.

## Rúnhild (design)
New module `hugrgate/ensemble/provenance.py`:
- `record_ensemble_decision(store, state, spec, result,
  membership_events=None, ...)` — builds the record via
  `DecisionRecord.from_decision`, deep-copies the full
  `metadata["ensemble"]` block (strategy, members, ballots, weights,
  winner share, minority report) into
  `record.metadata["ensemble"]`, attaches the slice-117 membership
  event log when given, appends to the store, and returns the stored
  hash-chained record. Abstentions record fine; non-ensemble results
  get `recorded: False`.
- `find_ensemble_records(store, strategy=None, n=100)` — recent
  ensemble records, newest last, optional strategy filter.
- Slice-015 integrity chain comes free through `store.append`.

## Eldra (code)
Store deep-copies on append; returned record is the stored copy.

## Sólrún (tests)
`tests/test_ensemble_119_provenance.py` — 9 tests green:
success (full council detail recorded incl. minority report and
weights; membership events attached; 5-record chain intact with
unique hashes; strategy-filtered retrieval; non-ensemble results
marked recorded=False; redact_input keeps ensemble detail;
abstentions recordable),
failure (store type check, n validation),
boundary (raw records without an ensemble block are ignored by
the finder).
mypy clean.

## Védis (integrate)
- `record_ensemble_decision`, `find_ensemble_records` exported;
  consumes 114's minority report and 117's event log.

## Scribe
Committed `feat(gjallarbu-119): ensemble provenance`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/provenance.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_119_provenance.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_119_provenance.py -q` → 9 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
