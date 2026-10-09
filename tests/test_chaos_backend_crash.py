"""Slice 252 — backend crash injection tests."""

from __future__ import annotations

import threading

import pytest

from hugrgate.chaos import CRASH, LATENCY, FaultSpec, FaultyBackend
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _crasher(rate=1.0, seed=11, name="primary"):
    return FaultyBackend(StubBackend(name=name)).arm(
        FaultSpec(mode=CRASH, rate=rate, seed=seed))


# --- crash semantics ---------------------------------------------------------------

def test_crash_rate_one_always_raises_backend_unavailable():
    backend = _crasher(rate=1.0)
    for _ in range(5):
        with pytest.raises(BackendUnavailable, match="injected crash"):
            backend.evaluate({}, _spec())
    stats = backend.fault_stats()
    assert stats["crash"] == 5 and stats["clean"] == 0


def test_crash_rate_zero_never_fires():
    backend = _crasher(rate=0.0)
    result = backend.evaluate({}, _spec())
    assert result.value == "a"
    stats = backend.fault_stats()
    assert stats["crash"] == 0 and stats["clean"] == 1


def test_crash_is_recoverable_per_taxonomy():
    assert BackendUnavailable.recoverable is True
    err = BackendUnavailable("chaos: injected crash of backend 'x'")
    assert err.code == "backend_unavailable"


def test_seeded_crash_pattern_is_reproducible():
    def pattern(seed):
        backend = _crasher(rate=0.5, seed=seed)
        crashed = []
        for _ in range(20):
            try:
                backend.evaluate({}, _spec())
            except BackendUnavailable:
                crashed.append(True)
            else:
                crashed.append(False)
        return crashed
    assert pattern(42) == pattern(42)
    assert any(pattern(42)) and not all(pattern(42))  # mixed at rate 0.5
    assert pattern(42) != pattern(43)  # different seed, different pattern


def test_fault_spec_validation():
    with pytest.raises(SpecError, match="in \\[0, 1\\]"):
        FaultSpec(mode=CRASH, rate=1.5)
    with pytest.raises(SpecError, match="in \\[0, 1\\]"):
        FaultSpec(mode=CRASH, rate=-0.1)
    with pytest.raises(SpecError, match="unknown fault mode"):
        FaultSpec(mode="meteor-strike")


def test_unwired_mode_arm_is_rejected_honestly():
    backend = FaultyBackend(StubBackend())
    with pytest.raises(SpecError, match="not wired in this build"):
        backend.arm(FaultSpec(mode=LATENCY, rate=1.0))
    assert backend.armed_modes() == []


def test_arm_disarm_lifecycle():
    backend = FaultyBackend(StubBackend())
    backend.arm(FaultSpec(mode=CRASH, rate=1.0))
    assert backend.armed_modes() == [CRASH]
    assert "chaos_armed" in backend.health()
    assert backend.health()["chaos_armed"] == [CRASH]
    with pytest.raises(BackendUnavailable):
        backend.evaluate({}, _spec())
    backend.disarm(CRASH)
    assert backend.armed_modes() == []
    assert backend.evaluate({}, _spec()).value == "a"
    backend.arm(FaultSpec(mode=CRASH, rate=1.0)).disarm_all()
    assert backend.armed_modes() == []


def test_rearm_replaces_spec_and_reseeds():
    backend = FaultyBackend(StubBackend())
    backend.arm(FaultSpec(mode=CRASH, rate=1.0, seed=1))
    backend.arm(FaultSpec(mode=CRASH, rate=0.0, seed=1))  # re-arm: no crash
    assert backend.evaluate({}, _spec()).value == "a"


def test_wrapper_is_transparent():
    inner = StubBackend(name="real", value="b")
    backend = FaultyBackend(inner)
    assert backend.name == "real"
    assert backend.capabilities() == inner.capabilities()
    assert backend.supports(_spec()) is True
    assert backend.health()["backend"] == "real"
    assert backend.is_remote == inner.is_remote
    with pytest.raises(SpecError, match="wraps a Backend"):
        FaultyBackend("not-a-backend")  # type: ignore[arg-type]


def test_stats_reset():
    backend = _crasher(rate=1.0)
    with pytest.raises(BackendUnavailable):
        backend.evaluate({}, _spec())
    backend.reset_stats()
    assert backend.fault_stats() == {"clean": 0, "crash": 0}


def test_concurrent_evaluates_keep_stats_consistent():
    backend = _crasher(rate=0.5, seed=5)
    errors: list[Exception] = []
    def hammer():
        try:
            for _ in range(50):
                try:
                    backend.evaluate({}, _spec())
                except BackendUnavailable:
                    pass
        except Exception as e:  # noqa: BLE001 - collected, asserted below
            errors.append(e)
    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    stats = backend.fault_stats()
    assert stats["crash"] + stats["clean"] == 200


# --- integration: the fallback chain must route around the crash ---------------------

def test_fallback_chain_survives_crashed_primary():
    primary = _crasher(rate=1.0, name="primary")
    secondary = StubBackend(name="secondary", value="b")
    chain = FallbackChain([primary, secondary])
    result = chain.evaluate({}, _spec())
    assert result.value == "b"
    assert result.fallback_used is True
    trace = result.metadata["fallback_trace"]
    assert trace[0]["backend"] == "primary"
    assert "backend_unavailable" in trace[0]["error"]


def test_chain_abstains_when_every_backend_crashes():
    first = _crasher(rate=1.0, name="one")
    second = _crasher(rate=1.0, name="two")
    chain = FallbackChain([first, second])
    from hugrgate.errors import Abstention
    with pytest.raises(Abstention):
        chain.evaluate({}, _spec())
