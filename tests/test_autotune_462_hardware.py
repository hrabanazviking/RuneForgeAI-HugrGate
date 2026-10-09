"""Slice 462 — hardware-aware tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners.hardware import (
    HardwareAwareTuner,
    HardwareProfile,
    HardwareTier,
    detect_hardware,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store():
    s = ConfigStore()
    s.register(TunableParameter(name="pool_size", dtype="int", default=4,
                                lo=1, hi=256))
    s.register(TunableParameter(name="batch", dtype="int", default=8,
                                lo=1, hi=512))
    return s


def _tuner(hw=None, **kw):
    tiers = [HardwareTier(name="edge", min_cpu=1, min_memory_mb=0,
                          profile={"pool_size": 2, "batch": 4}),
             HardwareTier(name="server", min_cpu=8, min_memory_mb=16000,
                          profile={"pool_size": 64, "batch": 128}),
             HardwareTier(name="workstation", min_cpu=4, min_memory_mb=8000,
                          profile={"pool_size": 16, "batch": 32})]
    base = dict(objective_id="hw", tiers=tiers, seed=1)
    if hw is not None:
        base["injected_hardware"] = hw
    base.update(kw)
    return HardwareAwareTuner(**base)


def test_detect_hardware_real():
    hw = detect_hardware()
    assert hw.cpu_count >= 1
    assert hw.arch and hw.system


def test_tier_selection_most_demanding_match():
    big = HardwareProfile(cpu_count=32, memory_mb=64000.0,
                          arch="x86_64", system="Linux")
    t = _tuner(hw=big)
    assert t.select_tier(big).name == "server"
    mid = HardwareProfile(cpu_count=6, memory_mb=16000.0,
                          arch="x86_64", system="Linux")
    assert t.select_tier(mid).name == "workstation"
    small = HardwareProfile(cpu_count=2, memory_mb=2000.0,
                            arch="aarch64", system="Linux")
    assert t.select_tier(small).name == "edge"


def test_unknown_memory_matches_any_tier():
    hw = HardwareProfile(cpu_count=16, memory_mb=0.0, arch="x", system="y")
    t = _tuner(hw=hw)
    # memory unknown (0.0): memory requirement is waived, cpu decides
    assert t.select_tier(hw).name == "server"


def test_tune_proposes_tier_profile():
    hw = HardwareProfile(cpu_count=32, memory_mb=64000.0,
                         arch="x86_64", system="Linux")
    t = _tuner(hw=hw)
    prop = t.tune(_ctx(_store()))
    assert prop is not None
    assert prop.changes == {"pool_size": 64, "batch": 128}
    assert prop.evidence["tier"] == "server"
    assert prop.evidence["hardware"]["cpu_count"] == 32


def test_tune_silent_when_already_matching():
    hw = HardwareProfile(cpu_count=2, memory_mb=2000.0,
                         arch="aarch64", system="Linux")
    s = _store()
    s.apply({"pool_size": 2, "batch": 4})
    assert _tuner(hw=hw).tune(_ctx(s)) is None


def test_tune_proposes_only_differences():
    hw = HardwareProfile(cpu_count=6, memory_mb=16000.0,
                         arch="x86_64", system="Linux")
    s = _store()
    s.apply({"pool_size": 16})  # batch still differs
    prop = _tuner(hw=hw).tune(_ctx(s))
    assert prop is not None
    assert prop.changes == {"batch": 32}


def test_out_of_bounds_profile_value_rejected():
    tiers = [HardwareTier(name="x", min_cpu=1, min_memory_mb=0,
                          profile={"pool_size": 99999})]
    t = HardwareAwareTuner(objective_id="o", tiers=tiers, seed=1,
                           injected_hardware=HardwareProfile(
                               cpu_count=2, memory_mb=1000.0,
                               arch="x", system="y"))
    with pytest.raises(Exception):  # ParameterError from coerce
        t.tune(_ctx(_store()))


def test_bad_tiers_rejected():
    with pytest.raises(TunerError):
        HardwareAwareTuner(objective_id="o", tiers=[], seed=1)
    with pytest.raises(TunerError):
        HardwareAwareTuner(objective_id="o", tiers=[
            HardwareTier(name="a", min_cpu=1, min_memory_mb=0,
                         profile={"x": 1}),
            HardwareTier(name="a", min_cpu=2, min_memory_mb=0,
                         profile={"x": 2})], seed=1)
    with pytest.raises(TunerError):
        HardwareTier(name="", min_cpu=1, min_memory_mb=0,
                     profile={"x": 1})
    with pytest.raises(TunerError):
        HardwareAwareTuner(objective_id="", tiers=[
            HardwareTier(name="a", min_cpu=1, min_memory_mb=0,
                         profile={"x": 1})], seed=1)


def test_end_to_end_offline():
    hw = HardwareProfile(cpu_count=32, memory_mb=64000.0,
                         arch="x86_64", system="Linux")
    store = _store()
    c = OptimizationController(store=store)
    c.register_objective("hw", lambda values: 0.0)
    c.register_tuner(_tuner(hw=hw))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("pool_size") == 4  # offline: untouched
