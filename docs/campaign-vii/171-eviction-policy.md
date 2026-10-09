# Slice 171 — Model eviction policy

## Skald (what already existed)
- Slice 170's residency table tracked loaded models but had no
  policy deciding which ones leave under memory pressure.

## Rúnhild (design)
`hugrgate/runtimes/eviction.py`: the decision layer over the
residency table. `EvictionPolicy.select(entries, budget)` nominates
in priority order; `EvictionBudget` caps per-pass evictions and
protects named runtimes; `Evictor.run` applies a policy to a
`ResidencyManager` and reports (`EvictionReport` with evicted /
skipped-in-use / skipped-protected counts). Four policies:
`LRUPolicy(max_idle_s)`, `TTLPolicy(ttl_s)`,
`MemoryPressurePolicy(high_watermark_bytes, used_bytes_fn)` (LRU-
first while over the watermark; repeat `run()` while
`under_pressure()`), and `CompositePolicy` (union, first nominator
wins). Live leases (`refcount > 0`) are skipped unless a policy opts
into `evict_in_use`. Memory readings are injected; the default is
stdlib `resource` RSS with an explicit warning that it is process
memory, not VRAM (real VRAM needs a provider hook like NVML).

Design correction (folded back into slice 170's commit): writing
these policies exposed that unload-on-zero made eviction pointless —
nothing idle would ever stay resident. `release()` now keeps the
model warm at refcount zero; only `evict()` unloads.

## Eldra (what was built)
- `hugrgate/runtimes/eviction.py` (new): 4 policies, `Evictor`,
  `EvictionBudget`, `EvictionDecision`, `EvictionReport`.
- `hugrgate/runtimes/residency.py`: warm-cache `release()` + doc
  (amended into slice 170's commit).
- `tests/test_localrt_171_eviction.py` (new, 16 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_170_residency.py
tests/test_localrt_171_eviction.py -q` → 26 passed. `ruff` clean,
`mypy` clean.

## Védis (integration)
- Policies consume only `ResidencyManager.snapshot()`; `Evictor`
  drives `manager.evict()`. No runtime/backend changes.

## Scribe
Commit `feat(gjallarbu-171): model eviction policy` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- A real VRAM `used_bytes_fn` (NVML / torch.cuda) wired to
  `MemoryPressurePolicy` on a GPU host.
