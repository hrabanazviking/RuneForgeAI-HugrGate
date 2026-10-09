"""Slice 263 — network-loss simulation tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import (
    DOWN,
    UP,
    NetworkGuard,
    NetworkSimulator,
)
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, BackendUnavailable, SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


class RemoteStub(StubBackend):
    """A stub that behaves like a remote backend (counts calls)."""

    def __init__(self, name="remote", value="a", host=None):
        super().__init__(name=name, value=value)
        self.is_remote = True
        self.calls = 0
        self._host = host or name

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        return super().evaluate(state, spec, context)


# --- simulator ----------------------------------------------------------------------------------------

def test_simulator_partition_and_heal():
    net = NetworkSimulator()
    assert net.is_reachable("any-host") is True  # default: up
    net.set_down("host-a")
    assert net.is_reachable("host-a") is False
    assert net.down_hosts() == ["host-a"]
    net.partition({"host-a": UP, "host-b": DOWN, "host-c": DOWN})
    assert net.is_reachable("host-a") is True
    assert net.down_hosts() == ["host-b", "host-c"]
    net.set_all_up()
    assert net.down_hosts() == []
    with pytest.raises(SpecError, match="unknown network state"):
        net.partition({"host-x": "limbo"})


# --- guard -----------------------------------------------------------------------------------------------

def test_guard_blocks_unreachable_remote_fast():
    net = NetworkSimulator().set_down("gpu-farm")
    remote = RemoteStub(name="remote", host="gpu-farm")
    guarded = NetworkGuard(remote, net, host="gpu-farm")
    assert guarded.host == "gpu-farm"
    with pytest.raises(BackendUnavailable, match="network unreachable"):
        guarded.evaluate({}, _spec())
    assert remote.calls == 0  # never touched the dead host
    assert guarded.stats() == {"allowed": 0, "blocked": 1}
    assert guarded.health()["network_reachable"] is False


def test_guard_passes_through_when_up():
    net = NetworkSimulator()
    remote = RemoteStub(name="remote")
    guarded = NetworkGuard(remote, net, host="remote")
    assert guarded.evaluate({}, _spec()).value == "a"
    assert remote.calls == 1
    assert guarded.stats() == {"allowed": 1, "blocked": 0}


def test_guard_ignores_network_for_local_backends():
    net = NetworkSimulator().set_down("localhost")
    local = StubBackend(name="local")
    guarded = NetworkGuard(local, net, host="localhost")
    # Local backends never touch the network: the outage is irrelevant.
    assert guarded.evaluate({}, _spec()).value == "a"
    assert guarded.health()["network_reachable"] is True


def test_guard_heals_with_the_network():
    net = NetworkSimulator().set_down("gpu-farm")
    guarded = NetworkGuard(RemoteStub(host="gpu-farm"), net, host="gpu-farm")
    with pytest.raises(BackendUnavailable):
        guarded.evaluate({}, _spec())
    net.set_up("gpu-farm")
    assert guarded.evaluate({}, _spec()).value == "a"


def test_guard_arg_validation():
    net = NetworkSimulator()
    with pytest.raises(SpecError, match="wraps a Backend"):
        NetworkGuard("nope", net)  # type: ignore[arg-type]
    with pytest.raises(SpecError, match="needs a NetworkSimulator"):
        NetworkGuard(StubBackend(), "nope")  # type: ignore[arg-type]


# --- partial failure: the chain routes around the dead host -------------------------------------------------

def test_partial_failure_routes_to_survivors():
    net = NetworkSimulator()
    net.partition({"dead-host": DOWN, "live-host": UP})
    dead = NetworkGuard(RemoteStub(name="r1", host="dead-host"), net,
                       host="dead-host")
    live = NetworkGuard(RemoteStub(name="r2", host="live-host"), net,
                       host="live-host")
    local = StubBackend(name="local", value="b")
    chain = FallbackChain([dead, live, local])
    result = chain.evaluate({}, _spec())
    assert result.value == "a"  # live remote served
    assert result.fallback_used is True
    assert result.metadata["decided_by"] == "r2"


def test_total_loss_falls_back_to_local():
    net = NetworkSimulator()
    net.partition({"h1": DOWN, "h2": DOWN})
    remotes = [NetworkGuard(RemoteStub(name=f"r{i}", host=f"h{i}"), net,
                            host=f"h{i}")
               for i in (1, 2)]
    chain = FallbackChain([*remotes, StubBackend(name="local", value="b")])
    result = chain.evaluate({}, _spec())
    assert result.value == "b"
    assert result.metadata["decided_by"] == "local"


# --- the policy is never silently weakened ----------------------------------------------------------------------

def test_network_loss_does_not_weaken_policy():
    policy = DecisionPolicy(remote_inference=True, minimum_probability=0.9)
    net = NetworkSimulator().set_down("gpu-farm")
    guarded = NetworkGuard(RemoteStub(name="remote", host="gpu-farm"), net)
    gate = HugrGate()
    gate.register(guarded)
    gate.register(StubBackend(name="local"))
    before_remote = policy.remote_inference
    before_threshold = policy.minimum_probability
    # Local stub answers at probability 1.0 — fine. Now force the
    # policy bar above what any backend offers: the gate must abstain,
    # not lower the bar because the network died.
    strict = DecisionPolicy(remote_inference=True, minimum_probability=0.999)
    low = StubBackend(name="low", probability=0.5)
    gate2 = HugrGate()
    gate2.register(low)
    with pytest.raises(Abstention):
        gate2.decide({}, _spec(), policy=strict, backend_name="low")
    assert policy.remote_inference is before_remote
    assert policy.minimum_probability == before_threshold
    assert strict.minimum_probability == 0.999  # untouched


def test_policy_still_blocks_remote_when_not_allowed():
    # Even with the network up, policy.remote_inference=False keeps
    # remote backends out — the network simulator changes nothing here.
    net = NetworkSimulator()
    guarded = NetworkGuard(RemoteStub(name="remote", host="h"), net)
    gate = HugrGate()
    gate.register(guarded)
    policy = DecisionPolicy(remote_inference=False)
    with pytest.raises(BackendUnavailable, match="blocked by policy"):
        gate.decide({}, _spec(), policy=policy, backend_name="remote")
