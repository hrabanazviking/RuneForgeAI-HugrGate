# Slice 385 — Human-review routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_385_human_review.py` (7 tests)

## What already existed

Escalation (384) climbs to `human` but there was no inbox —
tickets arrived with no queue, no SLA, no timeout behavior.

## What was built

- `hugrgate/agents/human_review.py` — `HumanReviewQueue`: enqueue
  with severity + SLA (queue ordered severity → arrival), decide
  with reviewer identity (double decisions raise), `overdue()`
  detection, `sweep()` timeout policies — `auto_deny` /
  `auto_approve` (recorded as `timeout-policy`), `escalate`
  (left pending for the caller), `raise` (raises
  `HumanReviewTimeout` naming every overdue item).
- Lifecycle bus signals (`review.enqueued` / `review.decided` /
  `review.overdue`) with trace continuity for notification gating
  and provenance.

## Verification

`pytest tests/test_agents_385_human_review.py` — 7 passed
(severity ordering, overdue boundaries, all four timeout
policies, double-decision rejection, bus lifecycle). `ruff
check` clean, `mypy` clean.
