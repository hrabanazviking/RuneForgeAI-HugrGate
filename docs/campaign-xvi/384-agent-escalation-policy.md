# Slice 384 — Agent escalation policy

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_384_escalation.py` (7 tests)

## What already existed

No ladder for stuck tickets: agents either spun or failed
silently. The error taxonomy already had `AgentEscalationFailed`
waiting for a raiser.

## What was built

- `hugrgate/agents/escalation.py` — `EscalationPolicy` over the
  ladder `agent → supervisor → human → terminal`. One rung per
  call (explicit higher targets allowed, never downward); depth
  capped by the agent's contract `max_escalation_depth`
  (default 3 when the contract is unknown); per-ticket cooldown
  refuses flapping; `terminal` is final. Every escalation emits
  `agent.escalated` on the bus with trace continuity (feeds
  triage's urgent rules, notification gating, provenance).
  Per-ticket history queryable for replay.
- Failures raise `AgentEscalationFailed` with details (max depth,
  cooldown) — the ticket stays with its current owner and can
  retry after cooldown.

## Verification

`pytest tests/test_agents_384_escalation.py` — 7 passed (ladder
climb, explicit target, terminal finality, contract depth cap,
cooldown boundary at exactly 30s, bus signal). `ruff check`
clean, `mypy` clean.
