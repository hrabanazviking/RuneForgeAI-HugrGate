# Slice 126 — Routing telemetry dataset

**Status:** complete. **Tests:** `tests/test_adaptive_telemetry.py` — 23 tests green.

## What existed before

No telemetry concept anywhere in the repo. Provenance (`hugrgate/provenance.py`)
records *decisions* with a hash chain, but nothing logged routing *context* —
features seen, candidates considered, propensities, policy version — the raw
material Campaign VI's mission ("learn which inference path works best for each
workload") requires.

## What was built

`hugrgate/adaptive/telemetry.py` — the learning substrate for the whole campaign:

- `RouteEvent`: one logged routing decision. Validates invariants at the
  boundary — chosen ∈ candidates, propensities sum to 1 with positive mass on
  the chosen arm (needed for IPS later), quality/cost/latency/energy ranges,
  JSON-serializability — raising `SpecError` instead of corrupting the log.
- `TelemetryStore`: append-only JSONL log (`adaptive-telemetry/v1` schema
  stamp). Outcomes arrive as separate `outcome` lines merged on read, so
  decision lines are immutable; `max_records` evicts oldest-first;
  `export`/`import_file` round-trip; corrupt lines and foreign schemas are
  rejected loudly on load.

## Integration

- Error semantics: `hugrgate.errors.SpecError` for malformed events,
  `KeyError` for unknown request ids (a bug, not a guess).
- Provenance-adjacent: append-only, immutable history mirrors
  `ProvenanceStore`'s integrity model.

## Verification

- `pytest tests/test_adaptive_telemetry.py` — 23/23 green (success, failure,
  boundary: bad propensities, duplicate ids, double outcomes, corrupt JSONL,
  schema mismatch, eviction, defensive copies).
- `mypy hugrgate/adaptive` — clean.
