# Slice 471 — Optimization reproducibility

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_471_repro.py` (6 tests)

## What existed

Tuning runs were fire-and-forget: no manifest captured what ran, so
no run could ever be replayed or audited for determinism.

## What changed

- `hugrgate/autotune/repro.py`:
  - `RunManifest`: run id, seed, mode, tuner dataclass configs,
    objective ids + callable refs, constraint refs, data
    fingerprint, config-before snapshot + hash, recorded proposal
    signatures, code version — JSON-serializable with
    corruption-checked `from_dict`;
  - `record_manifest()`: captures a manifest from a finished run
    (proposals supplied from the mode driver's journal);
  - `verify_replay()`: rebuilds via a caller factory, restores the
    config-before snapshot, re-runs with the recorded seed/mode,
    and compares proposal signatures change-for-change, returning a
    `match` verdict; code-version mismatch raises
    `ReproducibilityError`;
  - `snapshot_bundle`/`restore_bundle`: canonical deterministic
    config snapshots;
  - honest limits recorded: opaque callables replay by qualified
    name, so replay needs the same code version.
- `OfflineDriver` gains `seen` (proposal_id → Proposal) so replays
  can resolve what each proposal changed.

## Verification

6 new tests (replay match on identical rebuild, mismatch on
tampered config-before, manifest round-trip, corrupt manifest,
version mismatch, bundle round-trip/corruption); `ruff` and `mypy`
clean.
