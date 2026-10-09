"""Tests for slice 220 — offline peer recovery."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import decode_message
from hugrgate.cluster.recovery import (
    DEFAULT_RECOVERY_BASE_DELAY_S,
    DEFAULT_RECOVERY_MAX_DELAY_S,
    RecoveryManager,
)
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import BackendError, SpecError
from hugrgate.server import build_gate


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


class _Fail(httpx.BaseTransport):
    def handle_request(self, request):
        raise httpx.ConnectError("down")


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _peer(node):
    return PeerRecord(node_id=node.node_id, host="h", port=1,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- manager unit ------------------------------------------------------------------

def test_rejects_bad_config():
    with pytest.raises(SpecError):
        RecoveryManager(base_delay_s=0)
    with pytest.raises(SpecError):
        RecoveryManager(base_delay_s=10.0, max_delay_s=1.0)


def test_backoff_doubles_and_caps():
    clock = _Clock()
    manager = RecoveryManager(base_delay_s=2.0, max_delay_s=10.0,
                              clock=clock)
    assert manager.backoff_s("p") == 0.0
    assert manager.should_retry("p")
    manager.note_failure("p")
    assert manager.backoff_s("p") == 2.0
    manager.note_failure("p")
    assert manager.backoff_s("p") == 4.0
    manager.note_failure("p")
    assert manager.backoff_s("p") == 8.0
    manager.note_failure("p")
    assert manager.backoff_s("p") == 10.0  # capped
    assert manager.consecutive_failures("p") == 4
    assert manager.dark_peers() == ["p"]


def test_retry_timing():
    clock = _Clock()
    manager = RecoveryManager(base_delay_s=5.0, clock=clock)
    manager.note_failure("p")
    manager.mark_attempt("p")
    assert not manager.should_retry("p")
    assert manager.retry_after_s("p") == pytest.approx(5.0)
    clock.now += 4.9
    assert not manager.should_retry("p")
    clock.now += 0.2
    assert manager.should_retry("p")
    assert manager.retry_after_s("p") == 0.0


def test_success_clears_backoff():
    manager = RecoveryManager()
    manager.note_failure("p")
    manager.note_failure("p")
    manager.note_success("p")
    assert manager.consecutive_failures("p") == 0
    assert manager.backoff_s("p") == 0.0
    assert manager.dark_peers() == []
    assert manager.should_retry("p")


def test_constants():
    assert DEFAULT_RECOVERY_BASE_DELAY_S == 1.0
    assert DEFAULT_RECOVERY_MAX_DELAY_S == 300.0


# --- node integration ------------------------------------------------------------------

def test_decide_remote_feeds_recovery(spec):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = _peer(node_b)
    node_a.decide_remote(peer, spec, {"text": "a"},
                         policy=DecisionPolicy(remote_inference=True))
    assert node_a.recovery.consecutive_failures(peer.node_id) == 0

    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Fail()))
    with pytest.raises(BackendError):
        node_a.decide_remote(peer, spec, {"text": "a"},
                             policy=DecisionPolicy(remote_inference=True))
    assert node_a.recovery.consecutive_failures(peer.node_id) == 1
    assert peer.node_id in node_a.recovery.dark_peers()


def test_recover_peer_failure_backs_off():
    clock = _Clock()
    node_a, node_b = _node("a"), _node("b")
    node_a.recovery = RecoveryManager(base_delay_s=10.0, clock=clock)
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Fail()))
    peer = _peer(node_b)
    assert node_a.recover_peer(peer) is False
    assert node_a.recovery.consecutive_failures(peer.node_id) == 1
    # Backoff not elapsed: no retry attempted.
    assert node_a.recover_peer(peer) is False
    assert node_a.recovery.consecutive_failures(peer.node_id) == 1


def test_recover_peer_success_resets_everything():
    clock = _Clock()
    node_a, node_b = _node("a"), _node("b")
    node_a.recovery = RecoveryManager(base_delay_s=10.0, clock=clock)
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Fail()))
    peer = _peer(node_b)
    assert node_a.recover_peer(peer) is False
    # Poison every monitor, then revive the peer.
    for _ in range(10):
        node_a.health.record_failure(peer.node_id)
    node_a.latency.record(peer.node_id, 5000.0)
    node_a.costs.set_cost(peer.node_id, 42.0)
    assert node_a.health.is_quarantined(peer.node_id)

    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    clock.now += 11.0  # backoff elapsed
    assert node_a.recover_peer(peer) is True
    # Clean slate everywhere.
    assert node_a.recovery.consecutive_failures(peer.node_id) == 0
    assert node_a.health.stats(peer.node_id)["samples"] == 0
    assert not node_a.health.is_quarantined(peer.node_id)
    assert node_a.latency.stats(peer.node_id)["samples"] == 0
    assert node_a.costs.cost_of(peer.node_id) == 0.0
    assert node_a.partition.is_live(peer.node_id)


def test_recover_peer_never_raises():
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Fail()))
    peer = _peer(node_b)
    # Even repeated failures just lengthen the backoff.
    for _ in range(5):
        assert node_a.recover_peer(peer) is False
    assert node_a.recovery.backoff_s(peer.node_id) > 0


def test_propagate_policy_still_works():
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    from hugrgate.cluster.discovery import Discovery

    class _Static(Discovery):
        name = "test"

        def peers(self):
            return [_peer(node_b)]

    node_a.discovery.add_adapter(_Static())
    outcomes = node_a.propagate_policy()
    assert outcomes[node_b.node_id] == "ok"
