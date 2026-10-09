# Slice 066 — Early-exit routing

## What existed
Executors either climbed to the top or fanned out; none could stop
early on overwhelming confidence or on a stagnant climb.

## What changed
- **`hugrgate/routing/early_exit.py`** (new): `EarlyExitExecutor`
  reuses the serial walk's building blocks (`skip_reason`, `_attempt`,
  provenance, feedback hooks) with two exit rules:
  1. **Fast path**: probability ≥ `min(options.fast_path_probability,
     qos_profile.fast_path_probability)` → accepted immediately, even
     below the rung's stricter gate.
  2. **Diminishing returns**: after ≥3 attempts, if the best
     probability improved by < `early_exit_delta` (option or QoS
     profile; `0` disables) over the last 2 attempts → stop: accept
     the best if it clears `policy.minimum_probability`, else abstain
     early with `reason="early_exit_no_improvement"`.
  - Both exits recorded in audit detail + `metadata["early_exit"]`;
    the *best* rung's audit entry (not the last) is marked accepted;
    no double provenance logging (verified by test).

## Integration
Drop-in `RungExecutor`; `metadata["execution"] = "early_exit"`.

## Tests
`tests/test_routing_066.py` (7 tests): fast path below a strict rung
gate (later rung never attempted), normal gate clear carries no
early-exit marker, diminishing returns accepts the best and marks its
entry, stagnant climb stops after 3 (later rungs untouched),
no-improvement below policy minimum → early abstention, improving
climb runs to the end, single provenance record per attempt.

## Evidence
- `pytest tests/test_routing_066.py` → 7 passed.
