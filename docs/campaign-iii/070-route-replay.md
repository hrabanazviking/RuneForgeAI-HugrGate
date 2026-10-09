# Slice 070 — Route replay

## What existed
Climbs were ephemeral: once `decide()` returned, the only remnant was
the audit trail — no way to deterministically reproduce the decision
without re-running (and re-paying) the backends.

## What changed
- **`hugrgate/routing/replay.py`** (new):
  - `RouteRecording`: JSON-serializable capture — plan dict +
    fingerprint, spec type/options, policy minimum, per-rung outcomes
    (outcome, probability, latency, detail), winner index + full
    winner `DecisionResult` dict; `to_json`/`from_json` round-trip.
  - `RecordingExecutor`: wraps any executor; builds the recording
    from the executed decision (plan, audit, winner). Abstentions
    record nothing (no winner to reproduce).
  - `replay()` / `ReplayExecutor`: rebuild the plan, verify the
    fingerprint (tampering → `SpecError`), then walk the rungs using
    recorded probabilities and the recorded policy's gates — skips,
    errors, and abstentions replay authoritatively; the winner is
    reconstructed from its recorded dict. **No backend is ever
    touched** (verified with an empty registry). Replayed results
    carry `metadata["replayed"] = True`; replay latencies are recorded
    facts, not re-measurements (documented).

## Integration
Composes with every executor via wrapping; plans must be serializable
(DAG callables are refused at slice-068 construction time already).

## Tests
`tests/test_routing_070.py` (6 tests): record (skip + below-gate +
win) → replay reproduces winner/probability/value/audit with an empty
registry and zero backend calls; replay via executor; JSON round-trip;
tampered plan rejected by fingerprint; winner-less recording rejected;
abstention records nothing.

## Evidence
- `pytest tests/test_routing_070.py` → 6 passed.
