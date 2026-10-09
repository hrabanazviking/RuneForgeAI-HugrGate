# Slice 073 — Routing fuzz tests

## What existed
No adversarial coverage: backends were assumed to either return valid
results or raise documented errors.

## What changed
- **`hugrgate/routing/fuzz.py`** (new): stdlib-only seeded harness.
  `FuzzBackend` draws from ten behaviors (honest, weak, raiser with
  `BackendError`/`RuntimeError`/`ValueError`, unavailable, abstainer,
  probability liar, distribution liar, NaN probability, slow, None
  return). `run_fuzz(seed, iterations)` checks four invariants per
  iteration: (1) only `HugrGateError` escapes `decide()`; (2) returned
  results validate and carry trace/plan metadata; (3) audit outcomes
  are known strings with valid rung indices and `last_audit` matches;
  (4) determinism — the identical `(seed, it)` replays identically
  (every RNG derives from `(seed, it)` / `(seed, it, name)`).
- **`hugrgate/ladder.py`** (real bug found by the fuzzer): a backend
  returning `None` from `evaluate()` escaped `_attempt` as an
  `AttributeError` on `result.latency_ms`. Now audited as
  `RUNG_ERROR` ("backend returned None instead of a DecisionResult")
  and the climb continues.

## Adversarial tests
`tests/test_routing_073.py`: 3 fixed seeds × 60 iterations with zero
violations; targeted hostile backends (raiser/liar/NaN/None) contained
as audited `backend_error` → `Abstention`, never crashing; hostile rung
followed by honest rung still climbs; lying `p=1.5` never accepted even
with gate 0.0.

## Evidence
- `pytest tests/test_routing_073.py tests/test_ladder.py` → 72 passed.
