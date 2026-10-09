# Slice 059 — Memory-aware routing

## What existed
Routing never considered memory footprint: an 8GB model and a 256MB
model were interchangeable in every ladder.

## What changed
- **`hugrgate/routing/memory.py`** (new):
  - `MemoryModel`: footprint in MB from `hardware_requirements()`
    `["memory_mb"]`, else an optional `estimated_memory_mb()` method,
    else documented defaults (local 512MB, remote 0MB client-side —
    server memory is unobservable from here).
  - `MemoryAwarePlanner`: per-rung peak pruning — a rung survives iff
    its estimate ≤ `budget_mb` (explicit) or `options.max_memory_mb`;
    with no budget, rungs are annotated (`params["memory_estimate_mb"]`)
    but never pruned. Boundary: estimate == budget survives.

## Integration
Planner-side only; execution, validation, provenance, privacy,
abstention unchanged. Composes with the other aware-planners by
wrapping.

## Tests
`tests/test_routing_059.py` (7 tests): model resolution order
(declared → method → defaults, remote vs local), over-budget pruning,
boundary equality, no-budget annotation-only, options-budget fallback,
negative-budget rejection, empty plan → `Abstention`, end-to-end win by
the fitting rung.

## Evidence
- `pytest tests/test_routing_059.py` → 7 passed.
