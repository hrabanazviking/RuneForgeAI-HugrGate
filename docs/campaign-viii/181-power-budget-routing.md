# Slice 181 — Power-budget routing

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_power.py` (15 tests, green)

## What existed before

Slice 180 routed on temperature alone; a cool-running but
power-hungry backend could still brown out a Pi on a weak supply.

## What was built

- **`hugrgate/edge/power.py`** —
  - `PowerSource` ABC; `SysfsPowerSensor` reads hwmon power files
    (µW vs mW auto-detected, first readable file wins, injectable
    glob); `MockPowerSource` replays scripted draws;
  - `PowerBudget(budget_mw, reserve_mw, source=None)` — milliwatt
    ledger: named consumers, `remaining_mw()`, `utilization()`,
    `feasible(power_mw)` boundary checks; rejects oversize/duplicate/
    negative consumers with `PowerBudgetError`; `to_dict()` flags
    `open_loop` when no live source is attached (honest about
    declared-cost-only operation).
- **`EdgeRouter` extended** — optional `power=` budget: `route()`
  drops backends whose declared `power_mw` exceeds the remaining
  budget; backends declaring no power stay routable (ignorance is
  reported, not punished); thermal + power filters compose.

## Integration

- Same `hardware_requirements()["edge"]` cost block as slice 180 —
  one contract for both routing dimensions (Campaign VI energy
  objectives can extend it without touching the router).
- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended.

## Validation notes (Execution Law rule 13)

Declared `power_mw` figures are backend self-reports; open-loop
operation cannot catch lies. Live `power1_input` paths vary by board
and HAT — verify the sysfs glob on-device.

## Verification

- `pytest tests/test_edge_power.py tests/test_edge_thermal.py` — 32 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
