"""Tests for slice 223 — distributed chaos tests."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.chaos import ChaosProxy, FaultInjector
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import BackendError, SpecError
from hugrgate.server import build_gate


class _Static(Discovery):
    name = "test"

    def __init__(self, peers):
        self._peers = peers

    def peers(self):
        return list(self._peers)


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node
        self.received = 0

    def handle_request(self, request):
        self.received += 1
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _peer(node, port=1):
    return PeerRecord(node_id=node.node_id, host="h", port=port,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _chaos_client(caller, transport):
    caller.rpc = RPCClient(node_id=caller.node_id,
                           http_client=httpx.Client(transport=transport))


def _policy():
    return DecisionPolicy(remote_inference=True)


# --- injector unit -----------------------------------------------------------------

def test_rejects_bad_rates():
    for kwargs in ({"drop_rate": -0.1}, {"drop_rate": 1.1},
                   {"delay_rate": 2.0}, {"duplicate_rate": "x"},
                   {"corrupt_rate": float("nan")}, {"delay_s": -1.0}):
        with pytest.raises(SpecError):
            FaultInjector(**kwargs)


def test_deterministic_with_seed():
    a = FaultInjector(drop_rate=0.5, seed=42)
    b = FaultInjector(drop_rate=0.5, seed=42)
    assert [a.next_fault() for _ in range(50)] == \
           [b.next_fault() for _ in range(50)]


def test_zero_rates_never_fault():
    injector = FaultInjector()
    assert all(injector.next_fault() is None for _ in range(20))


def test_full_drop_rate():
    injector = FaultInjector(drop_rate=1.0, seed=1)
    assert all(f == "drop" for f in
               (injector.next_fault() for _ in range(10)))


def test_priority_drop_over_corrupt():
    injector = FaultInjector(drop_rate=1.0, corrupt_rate=1.0, seed=1)
    assert injector.next_fault() == "drop"


# --- proxy scenarios ------------------------------------------------------------------

def test_drop_storm_fails_over_to_healthy_peer(spec):
    from hugrgate import HugrGate
    # Empty local gate: the decision must travel the wire.
    node_a = ClusterNode(NodeIdentity.generate("a"), HugrGate())
    peer_x, peer_y = _node("x"), _node("y")
    inner = {2: _Loopback(peer_x), 3: _Loopback(peer_y)}
    node_a.discovery.add_adapter(
        _Static([_peer(peer_x, 2), _peer(peer_y, 3)]))
    # Drop whichever peer the router tries first (peers() is
    # freshest-first, not insertion order).
    first = next(c for c in node_a.router.route(spec, _policy())
                 if c.kind == "remote")
    drop_port = first.peer.port

    class _Router(httpx.BaseTransport):
        def handle_request(self, request):
            if request.url.port == drop_port:
                raise httpx.ConnectError("chaos: packet dropped")
            return inner[request.url.port].handle_request(request)

    _chaos_client(node_a, _Router())
    result = node_a.router.decide(spec, {"text": "a"}, policy=_policy())
    assert result.value in ("a", "b")
    assert result.metadata["route"]["kind"] == "remote"
    assert result.metadata["route"]["node_id"] != first.node_id
    # The dropped peer paid for it in health.
    assert node_a.health.stats(
        first.node_id)["total_failures"] >= 1


def test_drop_all_the_time_is_backend_error(spec):
    node_a, node_b = _node("a"), _node("b")
    proxy = ChaosProxy(_Loopback(node_b),
                       FaultInjector(drop_rate=1.0, seed=7))
    _chaos_client(node_a, proxy)
    with pytest.raises(BackendError, match="unreachable"):
        node_a.decide_remote(_peer(node_b), spec, {"text": "a"},
                             policy=_policy())
    assert proxy.stats()["drop"] == 1


def test_delay_shows_up_in_latency(spec):
    node_a, node_b = _node("a"), _node("b")
    proxy = ChaosProxy(_Loopback(node_b),
                       FaultInjector(delay_s=0.05, delay_rate=1.0, seed=3))
    _chaos_client(node_a, proxy)
    node_a.decide_remote(_peer(node_b), spec, {"text": "a"},
                         policy=_policy())
    stats = node_a.latency.stats(node_b.node_id)
    assert stats["ewma_ms"] >= 40.0  # the injected 50ms, minus slack
    assert proxy.stats()["delay"] == 1


def test_duplicate_delivers_twice_client_sees_once(spec):
    node_a, node_b = _node("a"), _node("b")
    inner = _Loopback(node_b)
    proxy = ChaosProxy(inner,
                       FaultInjector(duplicate_rate=1.0, seed=11))
    _chaos_client(node_a, proxy)
    result = node_a.decide_remote(_peer(node_b), spec, {"text": "a"},
                                  policy=_policy())
    assert result.value in ("a", "b")
    assert inner.received == 2  # delivered twice...
    assert proxy.stats()["duplicate"] == 1
    # ...and the client still got exactly one good answer.


def test_corrupt_envelope_is_rejected(spec):
    node_a, node_b = _node("a"), _node("b")
    proxy = ChaosProxy(_Loopback(node_b),
                       FaultInjector(corrupt_rate=1.0, seed=5))
    _chaos_client(node_a, proxy)
    with pytest.raises(SpecError):
        node_a.decide_remote(_peer(node_b), spec, {"text": "a"},
                             policy=_policy())
    assert proxy.stats()["corrupt"] == 1


def test_mixed_chaos_still_decides(spec):
    from hugrgate import HugrGate
    # Empty local gate: nothing local supports the spec, so every
    # decision must travel the (chaotic) wire. Drops, duplicates and
    # delays are all absorbed; corruption (typed SpecError) is covered
    # by test_corrupt_envelope_is_rejected.
    node_a = ClusterNode(NodeIdentity.generate("a"), HugrGate())
    peer_b, peer_c = _node("b"), _node("c")
    proxies = {2: ChaosProxy(_Loopback(peer_b), FaultInjector(
                   drop_rate=0.3, duplicate_rate=0.2,
                   delay_s=0.02, delay_rate=0.3, seed=99)),
               3: ChaosProxy(_Loopback(peer_c), FaultInjector(
                   drop_rate=0.3, duplicate_rate=0.2,
                   delay_s=0.02, delay_rate=0.3, seed=100))}

    class _Router(httpx.BaseTransport):
        def handle_request(self, request):
            return proxies[request.url.port].handle_request(request)

    _chaos_client(node_a, _Router())
    node_a.discovery.add_adapter(
        _Static([_peer(peer_b, 2), _peer(peer_c, 3)]))
    ok = 0
    for i in range(10):
        try:
            result = node_a.router.decide(spec, {"text": f"q{i}"},
                                          policy=_policy())
        except BackendError:
            # Both candidates dropped on the same round: the typed
            # "all candidates failed" outcome, not a hang.
            continue
        assert result.value in ("a", "b")
        ok += 1
    assert ok > 0  # the cluster kept deciding through the storm
    faults = sum(p.stats()["drop"] + p.stats()["duplicate"]
                 + p.stats()["delay"] for p in proxies.values())
    survived = sum(p.stats()["clean"] for p in proxies.values())
    assert faults > 0  # chaos happened
    assert survived > 0  # and calls survived it
    # Health tracking noticed the flakiness.
    failures = sum(node_a.health.stats(pid).get("total_failures", 0)
                   for pid in (peer_b.node_id, peer_c.node_id))
    assert failures >= 1


def test_proxy_stats_shape():
    proxy = ChaosProxy(_Loopback(_node()))
    assert proxy.stats() == {"drop": 0, "corrupt": 0, "duplicate": 0,
                            "delay": 0, "clean": 0}
    assert proxy.injector is not None
