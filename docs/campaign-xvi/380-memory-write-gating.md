# Slice 380 — Memory-write gating

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_380_memory_write.py` (9 tests)

## What already existed

`hugrgate.memory.access` maps roles to read/write permissions and
`hugrgate.privacy` owns the privacy ladder — but agents had no
mediated path to memory at all. Slice 380 gates the *write* path
(slice 381 gates reads).

## What was built

- `hugrgate/agents/memory_write.py` — `MemoryWriteGate`:
  `bind_agent(agent_id, role=..., clearance=...)` then
  `attempt_write(agent_id, episode)` checks, in order: episode
  declares a ladder privacy class → agent is bound (fail closed)
  → clearance covers the episode class → bound role grants writes
  (`ROLE_PERMISSIONS`: analysts/auditors are read-only) → payload
  size cap → dedup-key suppression → per-agent token-bucket rate
  limit. Grants consume quota and dedup state atomically.
- Denials carry machine-readable `reason` codes (`bad_class`,
  `unbound_agent`, `clearance`, `role_readonly`, `rate_limited`,
  `too_large`, `duplicate`) for the provenance graph (slice 396).
- The gate never touches the store — it only decides. The caller
  performs the write behind a granted `WritePermit`.

## Verification

`pytest tests/test_agents_380_memory_write.py` — 9 passed
(clearance ladder, read-only roles, rate refill, size cap, dedup
window, fail-closed unbound, stats). `ruff check` clean, `mypy`
clean.
