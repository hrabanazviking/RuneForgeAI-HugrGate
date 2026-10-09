"""Slice 264 — network-flap tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import (
    UP,
    NetworkGuard,
    NetworkSimulator,
)
from hugrgate.circuit import OPEN, CircuitRegistry
from hugrgate.errors import SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


class RemoteStub(StubBackend):
    def __init__(self, name="remote"):
        super().__init__(name=name)
        self.is_remote = True


@pytest.fixture
def clock():
    now = [0.0]
    return now, lambda: now[0]


# --- flap mechanics -----------------------------------------------------------------------------------

def test_flap_oscillates_on_period(clock):
    now, tick = clock
    net = NetworkSimulator().flap("h", period_s=10.0, up_fraction=0.5,
                                  clock=tick)
    assert net.flapping_hosts() == ["h"]
    expectations = [
        (0.0, True), (4.9, True), (5.0, False), (7.5, False),
        (9.9, False), (10.0, True), (14.9, True), (15.0, False),
        (20.0, True),
    ]
    for t, expected in expectations:
        now[0] = t
        assert net.is_reachable("h") is expected, f"t={t}"


def test_flap_fraction_boundaries(clock):
    now, tick = clock
    net = NetworkSimulator()
    net.flap("always-up", period_s=5.0, up_fraction=1.0, clock=tick)
    net.flap("always-down", period_s=5.0, up_fraction=0.0, clock=tick)
    for t in (0.0, 2.5, 4.9, 5.0, 12.3):
        now[0] = t
        assert net.is_reachable("always-up") is True
        assert net.is_reachable("always-down") is False


def test_flap_validation():
    net = NetworkSimulator()
    with pytest.raises(SpecError, match="period_s"):
        net.flap("h", period_s=0.0, up_fraction=0.5)
    with pytest.raises(SpecError, match="up_fraction"):
        net.flap("h", period_s=10.0, up_fraction=1.5)
    with pytest.raises(SpecError, match="up_fraction"):
        net.flap("h", period_s=10.0, up_fraction=-0.1)


def test_stop_flap_and_static_override(clock):
    now, tick = clock
    net = NetworkSimulator().flap("h", period_s=10.0, up_fraction=0.5,
                                  clock=tick)
    now[0] = 7.0
    assert net.is_reachable("h") is False
    net.stop_flap("h")
    assert net.flapping_hosts() == []
    assert net.is_reachable("h") is True  # statically up again
    # Explicit static states stop flaps too.
    net.flap("h", period_s=10.0, up_fraction=0.5, clock=tick)
    net.set_down("h")
    assert net.flapping_hosts() == []
    assert net.is_reachable("h") is False
    net.partition({"h": UP})
    assert net.is_reachable("h") is True
    net.set_all_up()
    assert net.down_hosts() == [] and net.flapping_hosts() == []


# --- flap + guard + breaker: the system rides the oscillation ---------------------------------------------

def test_flapping_remote_rides_breaker_half_open(clock):
    now, tick = clock
    net = NetworkSimulator().flap("h", period_s=10.0, up_fraction=0.5,
                                  clock=tick)
    guarded = NetworkGuard(RemoteStub("r1"), net, host="h")
    circuits = CircuitRegistry(failure_threshold=2, reset_timeout_s=5.0,
                               clock=tick)
    chain = FallbackChain([guarded, StubBackend(name="local", value="b")],
                          circuits=circuits)

    # t=0, host up: remote serves.
    now[0] = 0.0
    assert chain.evaluate({}, _spec()).value == "a"

    # t=6, host down: two failures trip the breaker...
    now[0] = 6.0
    assert chain.evaluate({}, _spec()).value == "b"
    assert chain.evaluate({}, _spec()).value == "b"
    assert circuits.get("r1").state == OPEN

    # ...further down-phase calls skip the remote fast (no more faults).
    blocked_before = guarded.stats()["blocked"]
    now[0] = 7.0
    result = chain.evaluate({}, _spec())
    assert result.value == "b"
    assert result.metadata["fallback_trace"][0]["reason"] == "circuit_open"
    assert guarded.stats()["blocked"] == blocked_before

    # t=11, host up again and breaker timeout elapsed: half-open probe
    # succeeds, breaker closes, remote serves.
    now[0] = 11.0
    assert chain.evaluate({}, _spec()).value == "a"
    assert circuits.get("r1").state != OPEN


def test_flap_never_weakens_policy(clock):
    now, tick = clock
    net = NetworkSimulator().flap("h", period_s=10.0, up_fraction=0.5,
                                  clock=tick)
    guarded = NetworkGuard(RemoteStub("r1"), net, host="h")
    chain = FallbackChain([guarded, StubBackend(name="local", value="b")])
    # Ride several full periods; every call is served by *some*
    # backend and policy thresholds are never touched.
    for i in range(40):
        now[0] = float(i)
        result = chain.evaluate({}, _spec())
        assert result.value in ("a", "b")
        assert result.accepted is True
    assert guarded.stats()["blocked"] > 0
    assert guarded.stats()["allowed"] > 0


def test_flap_with_zero_period_rejected_even_with_valid_fraction():
    net = NetworkSimulator()
    with pytest.raises(SpecError, match="period_s"):
        net.flap("h", period_s=-3.0, up_fraction=0.5)
