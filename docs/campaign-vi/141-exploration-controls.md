# Slice 141 — Exploration controls

**Status:** complete. **Tests:** `tests/test_adaptive_exploration.py` — 9 tests green.

## What existed before

The bandit's UCB explores by uncertainty, but there was no operator throttle:
no schedule, no budget, no kill switch.

## What was built

`hugrgate/adaptive/exploration.py`:

- `ExplorationConfig`: epsilon, epsilon_min, geometric decay, min pulls per
  arm, max exploration share, enabled flag — validated (epsilon_min ≤
  epsilon; decay ∈ (0,1]; shares ∈ [0,1]).
- `ExplorationControls`: `should_explore(arm_pulls)` — under-pulled arms
  always eligible (no starvation), otherwise a seeded uniform draw under
  epsilon; exploration never exceeds `max_exploration_share` of decisions;
  `disable()` kill-switch stops everything immediately; `snapshot()` makes
  the state auditable.
- Deterministic given a seed: same seed + history → same explore/exploit
  sequence.

## Integration

- Pure policy layer above the bandit; `SpecError` on invalid configs.

## Verification

- `pytest tests/test_adaptive_exploration.py` — 9/9 green: decay floors at
  epsilon_min, under-pulled forcing, budget cap enforcement, kill switch
  (even under-pulled arms stop), seed determinism with genuine stochasticity,
  snapshot fields, config serialization.
- `mypy hugrgate/adaptive` — clean.
