# Slice 396 — Agent provenance graph

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_396_provenance.py` (5 tests)

## What already existed

`hugrgate.provenance` tracks *what a decision was*; nothing
tracked *which agent decisions led to which* across the nervous
system.

## What was built

- `hugrgate/agents/provenance.py` — `AgentProvenanceGraph`: DAG
  of decision nodes (`route`, `dispatch`, `fuse`, `escalate`,
  `tool_call`, `review`, `gate`, ...). Parents must exist and
  node ids must be new — acyclic by construction, with
  `check_acyclic()` (Kahn's) for the release gate (400).
  `ancestors()` / `descendants()` / `lineage()` (every
  root-to-node path — "why did this happen?") / `export()`
  (topological, wire-safe JSON for replay, 397).

## Verification

`pytest tests/test_agents_396_provenance.py` — 5 passed
(validation, ancestor/descendant walks, diamond lineages,
acyclic check, topo export order, JSON wire-safety). `ruff
check` clean, `mypy` clean.
