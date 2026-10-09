# Slice 261 — Memory-pressure test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_memory_pressure.py` (9 tests, green)

## What existed before

Memory pressure was an edge-only story: slice 199's
`memory-pressure` scenario proved the edge cache shrinks and idle
models shed when RAM collapses. The general HugrGate path —
`DecisionCache`, batching, serving — had **no** pressure story at
all: under memory exhaustion it would just die.

## What was built

`hugrgate/chaos/resources.py` — deterministic resource-pressure
machinery for the core path:

- **`MemoryReading`** — total/available bytes with a
  `pressure_ratio` (0.0 → 1.0); validated at construction.
- **`MemoryPressureSimulator`** — scripted readings
  (`set_available` / `set_pressure_ratio`) so pressure tests are
  deterministic without touching the real machine.
- **`ResourceGuard`** — samples a reader callable and escalates
  `ok` → `warn` → `critical` across configured thresholds
  (defaults 0.75 / 0.90, validated `0 < warn < critical < 1`):
  - entering `warn` runs registered shed callbacks **once**
    (edge-triggered — sustained pressure doesn't re-shed every
    check);
  - entering `critical` additionally makes `allow_work()`
    return False: new work is refused until pressure recedes;
  - a raising shedder is logged, never fatal — shedding must not
    become a new failure mode.

## Integration

- The decision cache registers `cache.clear` as a shedder: under
  simulated warn the cache drops 50 entries to 0, keeps serving
  (miss → recompute), and recovers when pressure recedes — the
  core-path equivalent of the edge memory-pressure scenario.
- No production wiring yet (guards are opt-in, registered by the
  operator); the slice delivers the mechanism plus its proof.

## Verification

- 9 tests: reading/simulator validation; threshold escalation
  ok→warn→critical→ok with `allow_work` semantics; shed-on-entry
  only; unregister; failing shedder doesn't break escalation;
  cache shed integration; critical refusal + recovery.
- `ruff check` clean.
