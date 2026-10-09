# Slice 237 — Remote payload compiler

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_payload.py` (16 tests)

## What existed

No single chokepoint for outbound data: every privacy mechanism
built so far (labels, flow policy, minimization, local-only,
secrets, PII, redaction) was a standalone tool the caller had to
remember to invoke in the right order. Forgetting one stage — or
ordering them wrong — silently weakened the rest.

## What changed

- New module `hugrgate/privacy_payload.py`:
  - `RemotePayloadCompiler.compile(state, backend, policy)` — the
    eight-stage outbound pipeline: (1) attempt gate, (2) local-only
    enforcement, (3) data-flow policy, (4) minimization, (5)
    clearance filter, (6) secret scan, (7) PII scrub, (8) redaction
    pipeline. Denials raise (`PrivacyViolation`,
    `DataFlowDenied`, `SecretDetected`, `LocalOnlyViolation`).
  - `RemotePayload` — compiled payload plus a full audit manifest
    (backend, trust, jurisdiction, per-stage outcomes, flow
    decision, minimization report, stripped fields, PII findings,
    redactions). Deterministic and serializable.
  - Local backends get a documented passthrough (data never leaves
    the process).
- `PrivacyGuard.payload_compiler` + `compile_outbound` — the guard
  now owns the chokepoint hook (duck-typed; `privacy_payload`
  imports `privacy`, so no module-level import here).
- `PrivacyGuard.trust_level_for` / `jurisdiction_for` public aliases.
- Ladder integration: `LadderRouter._attempt` compiles remote-bound
  state through the guard's compiler before `backend.evaluate`;
  the manifest rides in `result.metadata["privacy_manifest"]`;
  compile denials are audited as `skipped_privacy_blocked`, not
  swallowed as rung errors. No compiler configured = behavior
  unchanged.
- Fixed `RedactionPipeline.apply_with_labels` to honor per-field
  redactors even without level strategies.

## Verification

- `pytest tests/test_privacy_payload.py` — 16 passed, including
  full-pipeline, determinism, non-mutation, all four denial types,
  ladder integration, and an adversarial secret-in-keep-list case
  (secret scan runs on the minimized payload).
- 272 tests across all privacy suites + ladder + errors green.
- `ruff check` clean; no import cycle.
