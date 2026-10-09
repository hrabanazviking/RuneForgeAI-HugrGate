"""Slice 254 — latency injection tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hugrgate.chaos import CRASH, LATENCY, FaultSpec, FaultyBackend
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend

ARTIFACT = Path(__file__).resolve().parent.parent / "benchmarks" / \
    "chaos-latency-254.json"


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _latent(delay_s=0.05, rate=1.0, seed=31):
    return FaultyBackend(StubBackend()).arm(
        FaultSpec(mode=LATENCY, rate=rate, seed=seed,
                  params={"delay_s": delay_s}))


# --- latency semantics -----------------------------------------------------------------

def test_injected_latency_is_observed():
    backend = _latent(delay_s=0.05)
    samples = []
    for _ in range(10):
        t0 = time.monotonic()
        result = backend.evaluate({}, _spec())
        samples.append(time.monotonic() - t0)
        assert result.value == "a"
    assert all(s >= 0.05 for s in samples)
    assert sum(samples) / len(samples) < 0.6  # no runaway sleep
    assert backend.fault_stats()["latency"] == 10


def test_baseline_without_fault_is_fast():
    backend = FaultyBackend(StubBackend())  # identical wrapper, clean
    t0 = time.monotonic()
    for _ in range(10):
        assert backend.evaluate({}, _spec()).value == "a"
    assert (time.monotonic() - t0) / 10 < 0.05
    assert backend.fault_stats()["clean"] == 10


def test_rate_zero_means_no_delay():
    backend = _latent(delay_s=0.2, rate=0.0)
    t0 = time.monotonic()
    backend.evaluate({}, _spec())
    assert time.monotonic() - t0 < 0.2


def test_delay_s_param_validation():
    backend = FaultyBackend(StubBackend())
    with pytest.raises(SpecError, match="'delay_s'"):
        backend.arm(FaultSpec(mode=LATENCY, params={}))
    with pytest.raises(SpecError, match="'delay_s'"):
        backend.arm(FaultSpec(mode=LATENCY, params={"delay_s": -0.5}))
    with pytest.raises(SpecError, match="'delay_s'"):
        backend.arm(FaultSpec(mode=LATENCY, params={"delay_s": "slow"}))
    backend.arm(FaultSpec(mode=LATENCY, params={"delay_s": 0}))
    assert backend.evaluate({}, _spec()).value == "a"  # zero delay is a no-op


def test_seeded_latency_pattern_is_reproducible():
    def delayed_calls(seed):
        backend = _latent(delay_s=0.02, rate=0.5, seed=seed)
        return [  # which calls were delayed
            (lambda t0: (backend.evaluate({}, _spec()),
                         time.monotonic() - t0 >= 0.02)[1])(time.monotonic())
            for _ in range(12)]
    assert delayed_calls(9) == delayed_calls(9)
    assert any(delayed_calls(9)) and not all(delayed_calls(9))


def test_crash_takes_priority_over_latency():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=CRASH, rate=1.0, seed=2))
               .arm(FaultSpec(mode=LATENCY, rate=1.0, seed=2,
                              params={"delay_s": 5.0})))
    t0 = time.monotonic()
    with pytest.raises(BackendUnavailable):  # crash wins; no 5s sleep
        backend.evaluate({}, _spec())
    assert time.monotonic() - t0 < 5.0
    assert backend.fault_stats().get("latency", 0) == 0


# --- measurement artifact (real numbers, committed) --------------------------------------

def test_measurement_artifact_schema_and_self_consistency():
    artifact = json.loads(ARTIFACT.read_text())
    assert artifact["schema"] == "hugrgate.chaos-latency/1"
    assert artifact["config"]["injected_delay_s"] == 0.05
    assert artifact["config"]["calls_per_arm"] == 30
    for arm in ("baseline", "injected"):
        for key in ("n", "mean_s", "min_s", "max_s", "stdev_s"):
            assert key in artifact[arm], (arm, key)
    comp = artifact["comparison"]
    assert comp["injected_min_ge_delay"] is True
    assert comp["baseline_max_lt_delay"] is True
    # The committed numbers must show the injected delay, honestly:
    # mean delta within [0.04, 0.2]s of the configured 0.05s.
    assert 0.04 <= comp["mean_delta_s"] <= 0.2
