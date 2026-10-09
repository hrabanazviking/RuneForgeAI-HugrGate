"""Slice 181 — power-budget routing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.backend import Backend
from hugrgate.edge.power import (
    MockPowerSource,
    PowerBudget,
    PowerBudgetError,
    SysfsPowerSensor,
)
from hugrgate.edge.routing import EdgeRouter
from hugrgate.edge.thermal import MockThermalSensor, ThermalGovernor
from hugrgate.result import DecisionResult


class EdgeBackend(Backend):
    def __init__(self, name: str, power_mw: float | None,
                 tclass: str = "cool"):
        self.name = name
        self._power = power_mw
        self._tclass = tclass
    def capabilities(self): return {}
    def supports(self, spec): return True
    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=0.9)
    def hardware_requirements(self):
        edge = {"thermal_class": self._tclass}
        if self._power is not None:
            edge["power_mw"] = self._power
        return {"edge": edge}


# --- sensors ------------------------------------------------------------------

def test_sysfs_power_sensor_microwatts(tmp_path: Path):
    f = tmp_path / "power1_input"
    f.write_text("2500000\n")  # 2.5 W in µW
    sensor = SysfsPowerSensor(path_glob=str(tmp_path / "power*"))
    assert sensor.read_mw() == pytest.approx(2500.0)


def test_sysfs_power_sensor_milliwatts(tmp_path: Path):
    f = tmp_path / "power1_input"
    f.write_text("1800\n")
    sensor = SysfsPowerSensor(path_glob=str(tmp_path / "power*"))
    assert sensor.read_mw() == pytest.approx(1800.0)


def test_sysfs_power_sensor_no_files(tmp_path: Path):
    sensor = SysfsPowerSensor(path_glob=str(tmp_path / "nope*"))
    assert sensor.read_mw() is None


def test_mock_power_source_replays_then_holds():
    src = MockPowerSource([100.0, None])
    assert src.read_mw() == 100.0
    assert src.read_mw() is None
    assert src.read_mw() is None
    with pytest.raises(ValueError):
        MockPowerSource([])


# --- budget: success --------------------------------------------------------------

def test_register_and_remaining():
    b = PowerBudget(5000.0, reserve_mw=1000.0)
    b.register_consumer("npu", 2000.0)
    assert b.committed_mw() == 2000.0
    assert b.remaining_mw() == pytest.approx(2000.0)
    assert b.utilization() == pytest.approx(0.5)
    assert b.deregister_consumer("npu") == 2000.0
    assert b.deregister_consumer("npu") == 0.0
    assert b.remaining_mw() == pytest.approx(4000.0)


def test_feasible_boundary():
    b = PowerBudget(5000.0, reserve_mw=1000.0)
    assert b.feasible(4000.0)
    assert not b.feasible(4000.01)


def test_live_draw_and_open_loop_flag():
    b = PowerBudget(5000.0, source=MockPowerSource([1234.0]))
    assert b.live_draw_mw() == 1234.0
    assert b.to_dict()["open_loop"] is False
    assert PowerBudget(5000.0).to_dict()["open_loop"] is True
    json.dumps(b.to_dict())


# --- budget: failure ----------------------------------------------------------------

def test_bad_construction_rejected():
    with pytest.raises(PowerBudgetError):
        PowerBudget(0)
    with pytest.raises(PowerBudgetError):
        PowerBudget(1000.0, reserve_mw=1000.0)
    with pytest.raises(PowerBudgetError):
        PowerBudget(1000.0, reserve_mw=-5.0)


def test_oversize_consumer_rejected():
    b = PowerBudget(5000.0, reserve_mw=1000.0)
    with pytest.raises(PowerBudgetError, match="exceeds usable budget"):
        b.register_consumer("hog", 4001.0)


def test_duplicate_and_negative_consumer_rejected():
    b = PowerBudget(5000.0)
    b.register_consumer("npu", 100.0)
    with pytest.raises(PowerBudgetError, match="already registered"):
        b.register_consumer("npu", 100.0)
    with pytest.raises(PowerBudgetError):
        b.register_consumer("neg", -1.0)
    with pytest.raises(PowerBudgetError):
        b.feasible(-1.0)


# --- router integration -------------------------------------------------------------------

def test_route_drops_over_budget_backends():
    budget = PowerBudget(2000.0)
    budget.register_consumer("base", 1500.0)  # 500 mW remain
    router = EdgeRouter(power=budget)
    cands = [EdgeBackend("hungry", 4000.0), EdgeBackend("lean", 300.0)]
    assert [b.name for b in router.route(cands)] == ["lean"]


def test_route_all_over_budget_returns_unfiltered():
    budget = PowerBudget(2000.0)
    router = EdgeRouter(power=budget)
    cands = [EdgeBackend("hungry", 4000.0)]
    assert router.route(cands) == cands


def test_route_unknown_power_allowed():
    budget = PowerBudget(2000.0)
    router = EdgeRouter(power=budget)
    cands = [EdgeBackend("mystery", None)]
    assert router.route(cands) == cands


def test_route_thermal_and_power_compose():
    gov = ThermalGovernor(MockThermalSensor([82.0]))  # hot
    budget = PowerBudget(10000.0)
    router = EdgeRouter(governor=gov, power=budget)
    cands = [EdgeBackend("hot-hungry", 100.0, "hot"),
             EdgeBackend("cool-lean", 100.0, "cool")]
    assert [b.name for b in router.route(cands)] == ["cool-lean"]


def test_route_without_power_behaves_as_before():
    router = EdgeRouter()
    cands = [EdgeBackend("a", 999999.0), EdgeBackend("b", 1.0)]
    # no budget attached: power never filters, ordering still by power
    assert [b.name for b in router.route(cands)] == ["b", "a"]
