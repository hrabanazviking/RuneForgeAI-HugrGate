"""Tests for slice 091 — calibration registry (rich catalog)."""

from __future__ import annotations

import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.registry import (
    CalibratorSpec,
    catalog,
    describe,
    find,
    register_spec,
    spec,
)
from hugrgate.errors import CalibrationError


def test_catalog_covers_legacy_registry():
    legacy = set(CalibratorRegistry.list())
    assert legacy >= {"platt", "isotonic", "temperature", "online",
                      "sliding-window", "beta-binomial", "constant-prior"}
    assert set(catalog()) >= legacy
    s = spec("platt")
    assert s.family == "parametric" and s.monotone is True
    assert s.needs_both_classes is True and s.streaming is False
    assert spec("online").streaming is True
    assert spec("beta-binomial").family == "bayesian"
    d = spec("temperature").as_dict()
    assert d["cls"].endswith("TemperatureCalibrator")
    assert isinstance(describe(), list) and len(describe()) >= 7


def test_find_filters():
    streaming = {s.name for s in find(streaming=True)}
    assert streaming == {"online", "sliding-window"}
    mono = {s.name for s in find(monotone=True)}
    assert {"platt", "isotonic", "temperature", "online"} <= mono
    assert {s.name for s in find(family="bayesian")} == {"beta-binomial"}
    both = {s.name for s in find(needs_both_classes=True)}
    assert both == {"platt", "temperature"}


def test_register_spec_and_deprecation():
    register_spec(CalibratorSpec(
        name="platt", cls=spec("platt").cls, family="parametric",
        monotone=True, needs_both_classes=True, streaming=False,
        deprecated=True, replaced_by="temperature",
        description="deprecated in favor of temperature"))
    assert spec("platt").deprecated is True
    assert "platt" not in {s.name for s in find()}
    assert "platt" in {s.name for s in find(include_deprecated=True)}
    # Restore for other tests.
    register_spec(CalibratorSpec(
        name="platt", cls=spec("platt").cls, family="parametric",
        monotone=True, needs_both_classes=True, streaming=False,
        description="Platt scaling."))
    assert "platt" in {s.name for s in find()}
    with pytest.raises(CalibrationError):
        spec("no-such-calibrator")
    with pytest.raises(CalibrationError):
        register_spec(CalibratorSpec(
            name="x", cls=spec("platt").cls, family="weird",
            monotone=True, needs_both_classes=True, streaming=False))
