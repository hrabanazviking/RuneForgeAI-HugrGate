"""Slice 134 — energy-quality objective tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.cost_quality import RoutingCandidate
from hugrgate.adaptive.energy_quality import (
    DEFAULT_LOCAL_WATTS,
    DEFAULT_REMOTE_WATTS,
    EnergyMeasurement,
    EnergyQualityObjective,
    estimate_energy_wh,
    measure_energy,
)
from hugrgate.errors import SpecError


def cand(name="a", quality=0.8, energy_wh=0.01):
    return RoutingCandidate(name=name, quality=quality, cost=0.0,
                            latency_ms=100.0, energy_wh=energy_wh)


# --- success ---------------------------------------------------------------

def test_leaner_wins_at_equal_quality():
    obj = EnergyQualityObjective(energy_scale=0.01)
    lean, hog = cand("lean", energy_wh=0.001), cand("hog", energy_wh=0.05)
    assert obj.score(lean) > obj.score(hog)
    assert obj.rank([hog, lean])[0].name == "lean"

def test_estimate_energy_wh_math():
    # 150 W for 1 hour = 150 Wh.
    assert estimate_energy_wh(3_600_000.0, 150.0) == pytest.approx(150.0)
    # Defaults are sane, documented estimates.
    assert DEFAULT_LOCAL_WATTS > DEFAULT_REMOTE_WATTS > 0

def test_measure_energy_pairs_latency_with_power_model():
    def work():
        time.sleep(0.002)
    m = measure_energy(work, watts=100.0, n_runs=5, label="w")
    assert isinstance(m, EnergyMeasurement)
    assert m.watts == 100.0
    assert m.mean_wh > 0
    assert m.p95_wh >= m.mean_wh
    # mean_wh is derived from the *measured* mean latency, not invented.
    assert m.mean_wh == pytest.approx(
        estimate_energy_wh(m.latency.mean_ms, 100.0))

def test_quality_can_outweigh_energy():
    obj = EnergyQualityObjective(quality_weight=10.0, energy_weight=1.0,
                                 energy_scale=0.01)
    great = cand("great", quality=1.0, energy_wh=0.05)
    meh = cand("meh", quality=0.5, energy_wh=0.001)
    assert obj.score(great) > obj.score(meh)

# --- failure ---------------------------------------------------------------

def test_bad_weights_rejected():
    with pytest.raises(SpecError):
        EnergyQualityObjective(energy_weight=-1.0)
    with pytest.raises(SpecError):
        EnergyQualityObjective(quality_weight=0.0, energy_weight=0.0)
    with pytest.raises(SpecError):
        EnergyQualityObjective(energy_scale=-0.5)

def test_estimate_guards_inputs():
    with pytest.raises(SpecError):
        estimate_energy_wh(-1.0, 150.0)
    with pytest.raises(SpecError):
        estimate_energy_wh(100.0, 0.0)
