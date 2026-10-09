# Slice 180 — Thermal-aware routing

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_thermal.py` (17 tests, green)

## What existed before

HugrGate routed to the first policy-allowed backend with no notion of
silicon temperature — on a Pi 4 in a closed case, sustained inference
invites kernel throttling that silently wrecks latency SLOs.

## What was built

- **`hugrgate/edge/thermal.py`** —
  - `ThermalSensor` ABC; `SysfsThermalSensor` reads
    `/sys/class/thermal/thermal_zone*/temp` (millidegrees tolerated,
    hottest zone wins, unreadable zones skipped); `MockThermalSensor`
    replays scripted readings then holds last;
  - `ThermalGovernor` — hysteresis-guarded level machine
    (`normal|warm|hot|critical`, 3 °C hysteresis so routing doesn't flap
    at the boundary); dead sensor (`None` reading) holds the last
    level; each level carries a derating factor (1.0 → 0.25).
- **`hugrgate/edge/routing.py`** — `EdgeRouter`, deliberately *beside*
  `HugrGate` rather than inside it (core routing untouched, backward
  compatible):
  - `route(candidates)` filters by thermal class
    (`cool|warm|hot`, declared via `Backend.hardware_requirements()`
    `"edge"` block; unknown → `warm`) and orders cool-first, then
    lowest power, then lowest latency;
  - never returns empty from a non-empty input — when everything is
    thermally forbidden it returns the list unfiltered so the *caller*
    decides whether to abstain;
  - `constrain_policy()` returns a narrowed policy *copy* (allowed
    backends pinned, latency cap scaled by derating), never mutating
    the input.

## Integration

- New `edge`-layer modules registered; maps + inventory regenerated.
- This is the Campaign VI adaptive-routing integration point: the
  router consumes the same `hardware_requirements()` contract any
  future energy-quality objective can extend.

## Validation notes (Execution Law rule 13)

Thresholds (70/85 °C) are Pi-ish defaults, not measurements; thermal
classes are backend self-declarations. On-device profiling tunes both.

## Verification

- `pytest tests/test_edge_thermal.py` — 17 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
