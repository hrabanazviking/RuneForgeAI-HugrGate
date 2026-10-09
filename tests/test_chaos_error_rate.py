"""Slice 255 — error-rate injection tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import CRASH, ERROR_RATE, HANG, LATENCY, FaultSpec, FaultyBackend
from hugrgate.circuit import OPEN, CircuitRegistry
from hugrgate.errors import BackendError, SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _flaky(rate=1.0, seed=41, **params):
    return FaultyBackend(StubBackend(name="flaky")).arm(
        FaultSpec(mode=ERROR_RATE, rate=rate, seed=seed, params=params))


# --- error-rate semantics -------------------------------------------------------------

def test_error_rate_one_always_raises_backend_error():
    backend = _flaky(rate=1.0)
    for _ in range(5):
        with pytest.raises(BackendError, match="injected backend error"):
            backend.evaluate({}, _spec())
    assert backend.fault_stats()["error_rate"] == 5
    assert BackendError.recoverable is True


def test_custom_message_param():
    backend = _flaky(message="disk exploded")
    with pytest.raises(BackendError, match="disk exploded"):
        backend.evaluate({}, _spec())
    with pytest.raises(SpecError, match="'message'"):
        FaultyBackend(StubBackend()).arm(
            FaultSpec(mode=ERROR_RATE, params={"message": "  "}))


def test_observed_rate_matches_configured_rate():
    backend = _flaky(rate=0.3, seed=99)
    errors = 0
    calls = 300
    for _ in range(calls):
        try:
            backend.evaluate({}, _spec())
        except BackendError:
            errors += 1
    observed = errors / calls
    assert 0.2 <= observed <= 0.4, f"observed rate {observed} far from 0.3"


def test_seeded_error_pattern_is_reproducible():
    def pattern(seed):
        backend = _flaky(rate=0.3, seed=seed)
        out = []
        for _ in range(60):
            try:
                backend.evaluate({}, _spec())
            except BackendError:
                out.append("E")
            else:
                out.append(".")
        return "".join(out)
    assert pattern(7) == pattern(7)
    assert pattern(7) != pattern(8)


def test_rate_zero_never_errors():
    backend = _flaky(rate=0.0)
    assert backend.evaluate({}, _spec()).value == "a"
    assert backend.fault_stats()["clean"] == 1


# --- priority ---------------------------------------------------------------------------

def test_crash_outranks_error_rate():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=CRASH, rate=1.0, seed=3))
               .arm(FaultSpec(mode=ERROR_RATE, rate=1.0, seed=3)))
    with pytest.raises(BackendError) as exc:
        backend.evaluate({}, _spec())
    assert exc.value.code == "backend_unavailable"  # crash, not error_rate


def test_hang_outranks_error_rate():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=HANG, rate=1.0, seed=3,
                              params={"hang_s": 0.01}))
               .arm(FaultSpec(mode=ERROR_RATE, rate=1.0, seed=3)))
    # hang wins: no BackendError, just the transient delay
    assert backend.evaluate({}, _spec()).value == "a"
    assert backend.fault_stats().get("error_rate", 0) == 0


def test_error_rate_outranks_latency():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=ERROR_RATE, rate=1.0, seed=3))
               .arm(FaultSpec(mode=LATENCY, rate=1.0, seed=3,
                              params={"delay_s": 5.0})))
    with pytest.raises(BackendError):  # error wins; no 5s sleep
        backend.evaluate({}, _spec())
    assert backend.fault_stats().get("latency", 0) == 0


# --- integration: circuit breaker trips on sustained errors ------------------------------

def test_circuit_breaker_opens_under_sustained_error_rate():
    flaky = _flaky(rate=1.0, seed=1)
    flaky.name = "flaky"  # breaker keyed by backend name
    circuits = CircuitRegistry(failure_threshold=3)
    chain = FallbackChain([flaky, StubBackend(name="steady", value="b")],
                          circuits=circuits)
    # First calls: errors recorded, breaker counts to threshold.
    for _ in range(3):
        assert chain.evaluate({}, _spec()).value == "b"
    breaker = circuits.get("flaky")
    assert breaker.state == OPEN
    # Now the breaker skips the flaky backend fast: no more error faults.
    before = flaky.fault_stats()["error_rate"]
    assert chain.evaluate({}, _spec()).value == "b"
    assert flaky.fault_stats()["error_rate"] == before
    trace = chain.evaluate({}, _spec()).metadata["fallback_trace"]
    assert trace[0]["outcome"] == "skipped"
    assert trace[0]["reason"] == "circuit_open"


def test_fallback_chain_routes_around_flaky_primary():
    flaky = _flaky(rate=1.0)
    chain = FallbackChain([flaky, StubBackend(name="backup", value="b")])
    result = chain.evaluate({}, _spec())
    assert result.value == "b"
    assert result.fallback_used is True
    assert result.metadata["decided_by"] == "backup"
