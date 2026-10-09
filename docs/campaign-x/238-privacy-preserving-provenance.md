# Slice 238 — Privacy-preserving provenance

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_provenance.py` (15 tests)

## What existed

Provenance had two modes: full state keys, or nothing (redacted).
There was no per-class policy, no way to prove what an input was
without storing it, and the redaction decision was reimplemented
ad-hoc in both `core.py` and `ladder.py`.

## What changed

- New module `hugrgate/privacy_provenance.py`:
  - `privacy_preserving_record(state, spec, result, policy, ...)` —
    builds a `DecisionRecord` whose state-derived metadata follows
    the class ladder: `public`/`standard`/`sensitive` keep state
    keys, `strict` is deep-redacted, `forbidden` carries no
    state-derived metadata at all. Every record carries a
    `privacy_class` marker.
  - `fingerprint_state` — deterministic per-field SHA-256
    fingerprints; opt-in for key modes, proving inputs without
    storing values.
  - `PrivacyAwareProvenanceStore` — `ProvenanceStore` subclass with
    one-call `append_decision`; the hash chain verifies identically
    over redacted/fingerprinted records.
- `hugrgate/core.py` and `hugrgate/ladder.py` now build records via
  `privacy_preserving_record`, replacing the duplicated ad-hoc
  redaction branches.

## Verification

- `pytest tests/test_privacy_provenance.py` — 15 passed.
- Adversarial: no raw values in any mode's metadata (including
  with fingerprints on); `forbidden` records still bind to state
  via `request_hash`; chain verifies over mixed-mode stores.
- `test_ladder.py`, `test_logging.py`,
  `test_provenance_integrity.py` (81) still green.
- `ruff check` clean.
