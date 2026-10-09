"""Slice 180 — thermal-aware routing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.backend import Backend
from hugrgate.edge.routing import EdgeRouter, edge_cost_of
from hugrgate.edge.thermal import (
    CRITICAL_C,
    WARN_C,
    MockThermalSensor,
    SysfsThermalSensor,
    ThermalGovernor,
    ThermalLevel,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult


class EdgeBackend(Backend):
    name = "edge-be"
    def __init__(self, tclass: str = "warm", power_mw: float = 1000.0,
                 latency: float = 50.0, name: str = "edge-be"):
        self.name = name
        self._tclass = tclass
        self._power = power_mw
        self._latency = latency
    def capabilities(self): return {}
    def supports(self, spec): return True
    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=0.9)
    def hardware_requirements(self):
        return {"edge": {"thermal_class": self._tclass,
                         "power_mw": self._power}}
    def estimated_latency(self): return self._latency


# --- sensors ----------------------------------------------------------------

def test_sysfs_sensor_reads_hottest_zone(tmp_path: Path):
    (tmp_path / "thermal_zone0" / "temp").parent.mkdir(parents=True)
    (tmp_path / "thermal_zone0" / "temp").write_text("45000\n")
    (tmp_path / "thermal_zone1").mkdir()
    (tmp_path / "thermal_zone1" / "temp").write_text("52000\n")
    sensor = SysfsThermalSensor(zone_glob=str(tmp_path / "thermal_zone*"))
    assert sensor.read_celsius() == pytest.approx(52.0)


def test_sysfs_sensor_skips_unreadable_zones(tmp_path: Path):
    (tmp_path / "thermal_zone0").mkdir()
    (tmp_path / "thermal_zone0" / "temp").write_text("not-a-number\n")
    sensor = SysfsThermalSensor(zone_glob=str(tmp_path / "thermal_zone*"))
    assert sensor.read_celsius() is None


def test_sysfs_sensor_empty_glob_returns_none(tmp_path: Path):
    sensor = SysfsThermalSensor(zone_glob=str(tmp_path / "nothing*"))
    assert sensor.read_celsius() is None


def test_mock_sensor_replays_then_holds():
    sensor = MockThermalSensor([40.0, None, 90.0])
    assert sensor.read_celsius() == 40.0
    assert sensor.read_celsius() is None
    assert sensor.read_celsius() == 90.0
    assert sensor.read_celsius() == 90.0  # holds last
    with pytest.raises(ValueError):
        MockThermalSensor([])


# --- governor -----------------------------------------------------------------

def test_governor_levels_and_derating():
    gov = ThermalGovernor(MockThermalSensor([30.0, 75.0, 80.0, 90.0]))
    assert gov.sample().level is ThermalLevel.NORMAL
    assert gov.sample().level is ThermalLevel.WARM
    assert gov.sample().level is ThermalLevel.HOT
    state = gov.sample()
    assert state.level is ThermalLevel.CRITICAL
    assert state.derating == pytest.approx(0.25)
    assert ThermalLevel.NORMAL.derating == 1.0


def test_governor_hysteresis_prevents_flap():
    # 71 °C -> warm; 69 °C stays warm (within 3 °C hysteresis); 66 °C -> normal
    gov = ThermalGovernor(MockThermalSensor([71.0, 69.0, 66.0]))
    assert gov.sample().level is ThermalLevel.WARM
    assert gov.sample().level is ThermalLevel.WARM
    assert gov.sample().level is ThermalLevel.NORMAL


def test_governor_dead_sensor_holds_level():
    gov = ThermalGovernor(MockThermalSensor([90.0, None]))
    assert gov.sample().level is ThermalLevel.CRITICAL
    state = gov.sample()
    assert state.level is ThermalLevel.CRITICAL
    assert state.temp_c is None


def test_governor_rejects_bad_thresholds():
    with pytest.raises(ValueError):
        ThermalGovernor(MockThermalSensor([1.0]), warn_c=90.0,
                        critical_c=80.0)
    with pytest.raises(ValueError):
        ThermalGovernor(MockThermalSensor([1.0]), hysteresis_c=-1.0)


def test_governor_state_serializes():
    gov = ThermalGovernor(MockThermalSensor([42.0]))
    json.dumps(gov.sample().to_dict())
    json.dumps(gov.to_dict())


# --- router ---------------------------------------------------------------------

def test_route_orders_cool_first_then_power():
    cands = [EdgeBackend("hot", 5000, 10, "hot-be"),
             EdgeBackend("cool", 300, 90, "cool-be"),
             EdgeBackend("warm", 800, 20, "warm-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([30.0])))
    assert [b.name for b in router.route(cands)] == \
        ["cool-be", "warm-be", "hot-be"]


def test_route_sheds_hot_backends_when_hot():
    cands = [EdgeBackend("hot", 5000, 10, "hot-be"),
             EdgeBackend("cool", 300, 90, "cool-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([82.0])))
    assert [b.name for b in router.route(cands)] == ["cool-be"]


def test_route_critical_only_cool():
    cands = [EdgeBackend("warm", 800, 20, "warm-be"),
             EdgeBackend("cool", 300, 90, "cool-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([95.0])))
    assert [b.name for b in router.route(cands)] == ["cool-be"]


def test_route_all_forbidden_returns_unfiltered():
    # The router never invents candidates, but it also never strands
    # the caller with an empty list when it started non-empty: the
    # *caller* decides whether to abstain.
    cands = [EdgeBackend("hot", 5000, 10, "hot-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([95.0])))
    assert router.route(cands) == cands
    assert router.route([]) == []


def test_route_unknown_thermal_class_defaults_warm():
    be = EdgeBackend("lava", 100, 10, "weird-be")
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([30.0])))
    assert router.route([be]) == [be]


def test_constrain_policy_narrows_and_tightens():
    cands = [EdgeBackend("hot", 5000, 10, "hot-be"),
             EdgeBackend("cool", 300, 90, "cool-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([82.0])))
    policy = DecisionPolicy(maximum_latency_ms=100.0)
    constrained = router.constrain_policy(policy, cands)
    assert constrained.allowed_backends == ["cool-be"]
    assert constrained.maximum_latency_ms == pytest.approx(50.0)
    # input policy untouched
    assert policy.allowed_backends is None
    assert policy.maximum_latency_ms == 100.0


def test_constrain_policy_normal_leaves_latency():
    cands = [EdgeBackend("cool", 300, 90, "cool-be")]
    router = EdgeRouter(ThermalGovernor(MockThermalSensor([30.0])))
    policy = DecisionPolicy(maximum_latency_ms=100.0)
    assert router.constrain_policy(policy, cands).maximum_latency_ms == 100.0


def test_edge_cost_of_tolerates_missing_block():
    class Plain(Backend):
        name = "plain"
        def capabilities(self): return {}
        def supports(self, spec): return True
        def evaluate(self, state, spec, context=None):
            return DecisionResult(value="a", probability=0.5)
    assert edge_cost_of(Plain()) == {}
    assert WARN_C < CRITICAL_C
