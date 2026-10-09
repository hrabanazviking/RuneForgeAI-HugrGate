"""Slice 141 — exploration controls tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.exploration import (
    ExplorationConfig,
    ExplorationControls,
)
from hugrgate.errors import SpecError

# --- success ---------------------------------------------------------------

def test_config_defaults_are_sane():
    cfg = ExplorationConfig()
    assert 0.0 < cfg.epsilon_min <= cfg.epsilon <= 1.0
    assert cfg.enabled is True

def test_epsilon_decays_toward_minimum():
    controls = ExplorationControls(
        ExplorationConfig(epsilon=0.5, epsilon_min=0.1, decay=0.5),
        seed=1)
    seen = set()
    for _ in range(10):
        controls.record_exploitation()
        seen.add(round(controls.epsilon, 6))
    assert controls.epsilon == pytest.approx(0.1)  # floored at minimum
    assert len(seen) > 1  # it actually decayed

def test_under_pulled_arms_force_exploration():
    controls = ExplorationControls(
        ExplorationConfig(epsilon=0.0, epsilon_min=0.0,
                          min_pulls_per_arm=3), seed=1)
    assert controls.should_explore({"a": 10, "b": 1}) is True
    assert controls.should_explore({"a": 10, "b": 3}) is False

def test_exploration_budget_cap():
    controls = ExplorationControls(
        ExplorationConfig(epsilon=1.0, max_exploration_share=0.5,
                          min_pulls_per_arm=0), seed=1)
    pulls = {"a": 100, "b": 100}
    # Spend the whole budget, then it must stop.
    for _ in range(10):
        controls.record_exploration()
    for _ in range(10):
        controls.record_exploitation()
    assert controls.exploration_share() == pytest.approx(0.5)
    assert controls.should_explore(pulls) is False

def test_kill_switch():
    controls = ExplorationControls(seed=1)
    assert controls.enabled is True
    controls.disable()
    assert controls.enabled is False
    assert controls.should_explore({"a": 0}) is False  # even under-pulled
    controls.enable()
    assert controls.should_explore({"a": 0}) is True

def test_deterministic_with_seed():
    def run():
        c = ExplorationControls(
            ExplorationConfig(epsilon=0.5, min_pulls_per_arm=0), seed=42)
        return [c.should_explore({"a": 5, "b": 5}) for _ in range(20)]
    assert run() == run()
    assert any(run()) and not all(run())  # genuinely stochastic

def test_snapshot_reports_state():
    controls = ExplorationControls(seed=1)
    controls.record_exploration()
    snap = controls.snapshot()
    assert snap["decisions"] == 1 and snap["explorations"] == 1
    assert snap["exploration_share"] == 1.0
    assert snap["config"]["epsilon"] == pytest.approx(0.1)

def test_config_serialization_round_trip():
    cfg = ExplorationConfig(epsilon=0.3, decay=0.99, enabled=False)
    cfg2 = ExplorationConfig.from_dict(cfg.to_dict())
    assert cfg2 == cfg

# --- failure ---------------------------------------------------------------

def test_bad_config_rejected():
    with pytest.raises(SpecError):
        ExplorationConfig(epsilon=1.5)
    with pytest.raises(SpecError):
        ExplorationConfig(epsilon=0.05, epsilon_min=0.1)
    with pytest.raises(SpecError):
        ExplorationConfig(decay=0.0)
    with pytest.raises(SpecError):
        ExplorationConfig(decay=1.5)
    with pytest.raises(SpecError):
        ExplorationConfig(min_pulls_per_arm=-1)
    with pytest.raises(SpecError):
        ExplorationConfig(max_exploration_share=2.0)
