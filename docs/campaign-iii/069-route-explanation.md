# Slice 069 — Route explanation

## What existed
Audit trails were machine-shaped lists of dicts; nothing turned a
climb into a human-readable account, and nothing narrated a plan
before execution.

## What changed
- **`hugrgate/routing/explain.py`** (new):
  - `OUTCOME_PHRASES`: plain-language phrasing for every `RUNG_*`
    outcome (a test asserts full coverage, so new outcomes can't slip
    through unexplained).
  - `explain_plan(plan)`: pre-execution narrative — fingerprint,
    strategy, per-rung gates/budgets/modes, each rung's `why`, plan
    rationale; empty plans narrated honestly.
  - `explain_route(audit, plan, winner)`: post-execution narrative —
    per-rung outcome + detail + probability + latency, attempted/
    skipped counts, total rung time, winner line.
  - `explain_decision(decision)`: one tied account.
  - Privacy: explanations name backends, gates, budgets, reasons —
    never raw state values (tested with a secret-bearing state).

## Integration
Pure narration over existing artifacts (plans, audits, decisions); no
routing behavior changed.

## Tests
`tests/test_routing_069.py` (7 tests): plan narrative content, empty
plan, real-climb route narrative (skip/below/accept phrasings, winner,
summary), secret non-leakage in route + plan text, empty audit,
outcome-phrase coverage over all `RUNG_*` constants, decision tying.

## Evidence
- `pytest tests/test_routing_069.py` → 7 passed.
