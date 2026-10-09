# Slice 190 — Edge cache tuning

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_cachetune.py` (11 tests, green)

## What existed before

`DecisionCache` took an absolute `max_size` — a number nobody derived
from the device. On a 512 MB board the default 1000 entries could be
fine or fatal depending on entry size; nothing connected the cache to
the memory-mode state machine.

## What was built

`hugrgate/edge/cachetune.py`:

- **`tune_cache(memory, entry_bytes_estimate, ttl_seconds)`** —
  derives `max_size` = (cache-component budget // entry estimate),
  clamped to `[16, 100_000]`; TTL scales with memory pressure
  (1.0×/0.5×/0.25× for standard/low/critical) so stale entries don't
  pin RAM the system needs back.
- **`cache_config_for_board(baseline)`** — static config from a Pi
  baseline's `recommended_cache_entries` (Pi 5 → 2000, Pi 3B+ → 250).
- **`EdgeCache`** — wraps a `DecisionCache`, subscribes to
  `MemoryManager.on_mode_change`, and rebuilds the cache on every
  mode transition. Entries are *dropped, never migrated* on retune —
  a mode change is exactly when RAM must be freed now. Full
  get/put/stats passthrough; stats embed the live config.

## Integration

- Second consumer of the slice-178 `on_mode_change` hook (with
  residency); board baselines from slice 177 feed the static path.
- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended.

## Validation notes (Execution Law rule 13)

`DEFAULT_ENTRY_BYTES` (4 KiB) is a conservative estimate — real
entry sizes should be measured per workload (slice 197) and passed
in.

## Verification

- `pytest tests/test_edge_cachetune.py` — 11 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
