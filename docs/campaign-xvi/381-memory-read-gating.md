# Slice 381 — Memory-read gating

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_381_memory_read.py` (7 tests)

## What already existed

Slice 380 gated writes; reads were unmediated. `GuardedHistory`
already encodes the role/redaction contract — the gate applies it
to agents.

## What was built

- `hugrgate/agents/memory_read.py` — `MemoryReadGate`:
  `bind_agent(agent_id, role=..., clearance=...)` then
  `attempt_read(agent_id, privacy_class, purpose=...)` checks class
  validity → binding (fail closed) → clearance → the role's
  `max_class` (an auditor with high clearance still can't read
  `sensitive`) → per-agent read rate limit. Reads at/above the
  role's `redact_at` line return `redacted=True` (caller must
  strip metadata/tags — the same contract `GuardedHistory`
  enforces).
- Bounded audit trail (configurable size, copies on read) of every
  decision with purpose strings, for the provenance graph (396)
  and human review (385).

## Verification

`pytest tests/test_agents_381_memory_read.py` — 7 passed
(redaction lines per role, role max_class vs clearance, audit
boundedness/copy-safety, rate limit). `ruff check` clean, `mypy`
clean.
