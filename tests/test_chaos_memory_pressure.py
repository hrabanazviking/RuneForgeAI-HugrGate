"""Slice 261 — memory-pressure simulation and guard tests."""

from __future__ import annotations

import pytest

from hugrgate.cache import DecisionCache
from hugrgate.chaos import (
    CRITICAL,
    OK,
    WARN,
    MemoryPressureSimulator,
    MemoryReading,
    ResourceGuard,
)
from hugrgate.errors import SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

# --- readings and simulator ----------------------------------------------------------------------

def test_reading_validation():
    with pytest.raises(SpecError, match="total_bytes"):
        MemoryReading(0, 0)
    with pytest.raises(SpecError, match="available_bytes"):
        MemoryReading(100, 101)
    with pytest.raises(SpecError, match="available_bytes"):
        MemoryReading(100, -1)
    reading = MemoryReading(100, 25)
    assert reading.pressure_ratio == pytest.approx(0.75)


def test_simulator_drives_pressure_deterministically():
    sim = MemoryPressureSimulator(total_bytes=1000)
    assert sim.info().pressure_ratio == pytest.approx(0.0)
    sim.set_pressure_ratio(0.8)
    assert sim.info().pressure_ratio == pytest.approx(0.8)
    sim.set_available(1000)
    assert sim.info().pressure_ratio == pytest.approx(0.0)
    with pytest.raises(SpecError, match="pressure ratio"):
        sim.set_pressure_ratio(1.5)
    with pytest.raises(SpecError, match="available_bytes"):
        sim.set_available(10_000)


# --- guard escalation -------------------------------------------------------------------------------

def test_guard_escalates_through_thresholds():
    sim = MemoryPressureSimulator(total_bytes=100)
    guard = ResourceGuard(sim.info, warn_ratio=0.5, critical_ratio=0.8)
    assert guard.state == OK and guard.allow_work() is True
    sim.set_pressure_ratio(0.5)
    assert guard.check() == WARN
    assert guard.allow_work() is True  # warn sheds; work continues
    sim.set_pressure_ratio(0.8)
    assert guard.check() == CRITICAL
    assert guard.allow_work() is False  # critical refuses new work
    sim.set_pressure_ratio(0.1)
    assert guard.check() == OK
    assert guard.allow_work() is True
    assert guard.transitions() == 3


def test_guard_threshold_validation():
    sim = MemoryPressureSimulator()
    with pytest.raises(SpecError, match="warn_ratio"):
        ResourceGuard(sim.info, warn_ratio=0.9, critical_ratio=0.8)
    with pytest.raises(SpecError, match="warn_ratio"):
        ResourceGuard(sim.info, warn_ratio=0.0, critical_ratio=0.8)


def test_shedders_run_on_entry_only():
    sim = MemoryPressureSimulator(total_bytes=100)
    guard = ResourceGuard(sim.info, warn_ratio=0.5, critical_ratio=0.8)
    shed: list[str] = []
    guard.register_shed("cache", lambda: shed.append("shed"))
    sim.set_pressure_ratio(0.6)
    guard.check()
    guard.check()  # sustained warn: no repeat shed
    guard.check()
    assert shed == ["shed"]
    sim.set_pressure_ratio(0.9)
    guard.check()  # warn -> critical is an entry: shed again
    assert shed == ["shed", "shed"]
    with pytest.raises(SpecError, match="non-empty"):
        guard.register_shed("  ", lambda: None)
    guard.unregister_shed("cache")
    sim.set_pressure_ratio(0.0)
    guard.check()
    sim.set_pressure_ratio(0.6)
    guard.check()
    assert shed == ["shed", "shed"]  # unregistered: silent


def test_failing_shedder_does_not_break_the_guard(caplog):
    sim = MemoryPressureSimulator(total_bytes=100)
    guard = ResourceGuard(sim.info)
    def bad_shed():
        raise RuntimeError("shedder exploded")
    guard.register_shed("bad", bad_shed)
    sim.set_pressure_ratio(0.99)
    assert guard.check() == CRITICAL  # escalation survived the shedder
    assert guard.allow_work() is False


# --- integration: the decision cache sheds under pressure ----------------------------------------------

def test_cache_sheds_under_memory_pressure():
    sim = MemoryPressureSimulator(total_bytes=100)
    guard = ResourceGuard(sim.info, warn_ratio=0.5, critical_ratio=0.8)
    cache = DecisionCache(ttl_seconds=600.0, max_size=1000)
    policy = DecisionPolicy()
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    guard.register_shed("decision-cache", cache.clear)
    for i in range(50):
        cache.put({"q": i}, spec, policy,
                  DecisionResult(value="a", probability=0.9, backend="b1"))
    assert len(cache) == 50
    sim.set_pressure_ratio(0.6)  # warn: shed
    assert guard.check() == WARN
    assert len(cache) == 0
    # A shed cache misses and recomputes; service continues under warn.
    assert cache.get({"q": 1}, spec, policy) is None
    assert guard.allow_work() is True


def test_guard_refuses_work_at_critical_but_recovers():
    sim = MemoryPressureSimulator(total_bytes=100)
    guard = ResourceGuard(sim.info, warn_ratio=0.5, critical_ratio=0.8)
    sim.set_pressure_ratio(0.95)
    guard.check()
    assert guard.allow_work() is False
    # Pressure recedes: work allowed again without restart.
    sim.set_pressure_ratio(0.2)
    assert guard.check() == OK
    assert guard.allow_work() is True
