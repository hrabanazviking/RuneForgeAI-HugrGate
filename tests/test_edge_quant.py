"""Slice 182 — quantized-model profiles tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.quant import (
    QUANT_PROFILES,
    QuantError,
    QuantFormat,
    QuantProfile,
    QuantProfileRegistry,
    estimate,
    select_profile,
)

# --- registry: success ------------------------------------------------------------

def test_canonical_profiles_pre_registered():
    reg = QuantProfileRegistry()
    assert set(reg.list()) == set(QUANT_PROFILES)
    assert len(reg) == 5
    int8 = reg.get("int8")
    assert int8.format is QuantFormat.INT8
    assert int8.to_dict()["planning_estimate"] is True


def test_register_custom_profile():
    reg = QuantProfileRegistry()
    reg.register(QuantProfile(name="int8-awq", format=QuantFormat.INT8,
                              size_factor=0.28, latency_factor=0.5))
    assert "int8-awq" in reg.list()


def test_register_replace():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="already registered"):
        reg.register(QuantProfile(name="int8", format=QuantFormat.INT8,
                                  size_factor=0.2, latency_factor=0.4))
    reg.register(QuantProfile(name="int8", format=QuantFormat.INT8,
                              size_factor=0.2, latency_factor=0.4),
                 replace=True)
    assert reg.get("int8").size_factor == 0.2


# --- registry: failure --------------------------------------------------------------

def test_unknown_profile_raises_with_known_list():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="known:"):
        reg.get("int2")


def test_register_non_profile_rejected():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="can only register"):
        reg.register("int8")  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs", [
    {"name": "", "format": QuantFormat.INT8,
     "size_factor": 0.25, "latency_factor": 0.5},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 0.0, "latency_factor": 0.5},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 0.25, "latency_factor": 0.0},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 2.0, "latency_factor": 0.5},
])
def test_invalid_profile_rejected(kwargs):
    with pytest.raises(QuantError):
        QuantProfile(**kwargs)


# --- estimate / select --------------------------------------------------------------

def test_estimate_scales_reference():
    est = estimate(QUANT_PROFILES["int8"], 4000.0, 200.0)
    assert est == {"size_mb": 1000.0, "latency_ms": 90.0}


def test_estimate_rejects_non_positive_base():
    with pytest.raises(QuantError):
        estimate(QUANT_PROFILES["int8"], 0.0, 200.0)


def test_select_profile_picks_smallest_fitting():
    reg = QuantProfileRegistry()
    # 4000 MB fp32 model, 200 ms fp32 latency; budget fits int8/int4
    chosen = select_profile(reg, ram_budget_mb=600.0,
                            latency_budget_ms=100.0,
                            base_size_mb=4000.0, base_latency_ms=200.0)
    assert chosen.name == "int4"  # smallest fitting


def test_select_profile_fastest_preference():
    reg = QuantProfileRegistry()
    chosen = select_profile(reg, ram_budget_mb=600.0,
                            latency_budget_ms=100.0,
                            base_size_mb=4000.0, base_latency_ms=200.0,
                            preference="fastest")
    assert chosen.name == "int4"  # also the fastest here


def test_select_profile_nothing_fits_raises():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="no quantization profile fits"):
        select_profile(reg, ram_budget_mb=10.0, latency_budget_ms=1.0,
                       base_size_mb=4000.0, base_latency_ms=200.0)


def test_select_profile_unknown_preference():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="unknown preference"):
        select_profile(reg, 600.0, 100.0, 4000.0, 200.0,
                       preference="prettiest")


def test_select_profile_respects_min_ram():
    reg = QuantProfileRegistry()
    # A profile whose byte size fits but whose min_ram_mb does not must
    # be skipped: min_ram models runtime overhead beyond the weights.
    reg.register(QuantProfile(name="int4-tiny", format=QuantFormat.INT4,
                              size_factor=0.01, latency_factor=0.3,
                              min_ram_mb=4096))
    with pytest.raises(QuantError, match="no quantization profile fits"):
        select_profile(reg, ram_budget_mb=300.0,
                       latency_budget_ms=1000.0,
                       base_size_mb=4000.0, base_latency_ms=200.0)
    # ...while a generous budget selects it, proving the profile is
    # otherwise viable and min_ram_mb was the gate.
    chosen = select_profile(reg, ram_budget_mb=5000.0,
                            latency_budget_ms=1000.0,
                            base_size_mb=4000.0, base_latency_ms=200.0)
    assert chosen.name == "int4-tiny"
