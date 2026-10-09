# Slice 065 — Hedged inference

## What existed
Executors were all-or-nothing on scheduling: strictly serial, or full
parallel fan-out. Nothing hedged — starting a backup only when the
primary proved slow.

## What changed
- **`hugrgate/routing/hedged.py`** (new): `HedgedPlanExecutor` —
  primary-first; if it hasn't finished within `options.hedge_delay_ms`,
  the next rung launches as a hedge alongside it. First gate-clear
  wins; stragglers are cancelled best-effort and audited as
  `RUNG_CANCELLED`. A rung completing below its gate hands off
  immediately (no waiting out the delay). When the QoS profile
  disallows hedging, the executor degrades to strict serial (unbounded
  wait, noted in the plan rationale). Prompt winner return via
  `shutdown(wait=False)` + a closed-flag that drops late straggler
  writes — verified by timing test.
- **`hugrgate/ladder.py`**: additive `RUNG_CANCELLED = "cancelled"`
  audit outcome (+ export).

## Integration
Same `skip_reason` / `_attempt` / provenance / feedback path as the
other executors; hedged launches marked `[hedged]` in audit detail.
`metadata["execution"] = "hedged"`.

## Tests
`tests/test_routing_065.py` (6 tests, timed): hedge beats a 0.4s
primary (returns well under 0.35s), no hedge when the primary is fast
(backup never launched), below-gate handoff ignores the delay,
QoS-disabled hedging goes serial, full-failure abstention, `[hedged]`
audit marking.

## Evidence
- `pytest tests/test_routing_065.py` → 6 passed.
- `pytest tests/test_ladder.py tests/test_routing_064.py` → 70 passed
  (no regressions from the new audit outcome).
