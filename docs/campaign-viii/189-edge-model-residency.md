# Slice 189 — Edge model residency

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_residency.py` (12 tests, green)

## What existed before

Slices 182–184 made models quantizable and measurable, but nothing
decided which models live in RAM — on a 512 MB Zero 2 W, loading two
models at once is an OOM crash waiting to happen.

## What was built

`hugrgate/edge/residency.py`:

- **`ModelEntry`** — catalog record: name, `size_bytes`, quant
  profile name, pinned flag, residency state, refcount, LRU stamp.
- **`ResidencyManager(ram_budget_bytes, memory=None)`** —
  - `register_model()` rejects oversize (can-never-fit), duplicate,
    and malformed entries;
  - `acquire()`/`release()` refcounted residency; acquire evicts LRU
    unpinned idle models until the newcomer fits, else raises
    `ResidencyError` naming budget vs used bytes;
  - pinned models are never evicted; in-use (refcount > 0) models are
    never evicted; `evict_idle()` sheds the rest;
  - subscribes to `MemoryManager.on_mode_change`: any degradation
    below `standard` immediately sheds idle models; `critical` mode
    additionally refuses non-pinned acquires (abstain, don't OOM);
    recovery never auto-reloads — the next `acquire()` does it
    on demand;
  - injectable clock for deterministic LRU tests; `status()` is JSON-
    serializable.

## Integration

- First consumer of the slice-178 `on_mode_change` hook (the
  integration point the memory slice promised); quant profile names
  on entries link to slice-182 planning (`Int4Adapter.storage_bytes`
  gives exact byte figures for registration).
- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended.

## Validation notes (Execution Law rule 13)

Budget figures must come from on-device measurement (slice 197),
not guesses. LRU is a policy choice; workload-specific pinning
strategies can layer on top.

## Verification

- `pytest tests/test_edge_residency.py` — 12 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
