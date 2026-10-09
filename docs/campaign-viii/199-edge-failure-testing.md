# Slice 199 — Edge failure testing

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_chaos.py` (6 tests, green)

## What existed before

Every edge component had unit tests, but nothing verified the
*failure stories* end to end — what actually happens when power dies
mid-write, the SoC spikes to 95 °C, the NPU vanishes, RAM collapses,
or flash wears out.

## What was built

`hugrgate/edge/chaos.py` — deterministic fault injection:

- **`FaultScenario`** (name, description, inject-and-verify callable)
  and **`ChaosRunner`** (register, `run_all`, JSON-serializable
  `report()`). A raising scenario is a recorded failure, never an
  abort — the report shows *all* outcomes.
- **Six built-in scenarios**, each hermetic (own components, own
  tmpdirs, scripted sensors):
  1. `power-loss-mid-write` — torn checkpoint skipped for the last
     good record;
  2. `thermal-spike` — 95 °C spike sheds hot backends from routing;
  3. `npu-dropout` — vanished NPU disappears from `detect_all()` and
     `best_for()`;
  4. `memory-pressure` — critical RAM shrinks the edge cache, sheds
     idle models, refuses non-pinned acquires;
  5. `flash-budget-exhaustion` — exhausted budget fails closed;
  6. `watchdog-starvation` — un-heartbeated loop records the miss and
     fires the policy.
- `run_builtin_scenarios()` executes all six; the report is
  assertion-checked JSON-serializable.

Two scenario bugs (mine, not the components') were caught while
building: a flash budget too generous to trigger, and a model that
was never released before the pressure spike — both fixed and
pinned by the now-passing scenarios.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. This is the executable half of slice
  200's release gate.

## Validation notes (Execution Law rule 13)

Simulated faults, not physical ones — real power-yank, thermal
chamber, and NPU hot-unplug testing still needed on-device.

## Verification

- `pytest tests/test_edge_chaos.py` — 6 passed (incl. all 6 scenarios green)
- `ruff check`, `mypy hugrgate/edge/` — clean
