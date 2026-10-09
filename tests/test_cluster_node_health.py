"""Tests for slice 213 — node health scoring."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.node_health import (
    DEFAULT_QUARANTINE_THRESHOLD,
    NodeHealthMonitor,
    PeerHealth,
)
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
    def __init__(self, node, fail=False):
        self.node = node
        self.fail = fail

    def handle_request(self, request):
        if self.fail:
            raise httpx.ConnectError("down")
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- monitor unit ---------------------------------------------------------------

def test_fresh_peer_scores_perfect():
    monitor = NodeHealthMonitor()
    assert monitor.score("new") == 1.0
    assert not monitor.is_quarantined("new")


def test_failures_drag_score_down():
    monitor = NodeHealthMonitor()
    for _ in range(3):
        monitor.record_success("p")
    monitor.record_failure("p")
    assert monitor.score("p") == pytest.approx(0.75)


def test_window_bounds_memory():
    monitor = NodeHealthMonitor(window=10)
    for _ in range(50):
        monitor.record_success("p")
    assert monitor.stats("p")["samples"] == 10


def test_quarantine_on_consecutive_failures():
    monitor = NodeHealthMonitor(max_consecutive_failures=3)
    for _ in range(3):
        monitor.record_failure("p")
    assert monitor.is_quarantined("p")
    assert monitor.score("p") == 0.0
    assert monitor.quarantined_peers() == ["p"]


def test_quarantine_on_low_window_score():
    monitor = NodeHealthMonitor(quarantine_threshold=0.5, window=4,
                                max_consecutive_failures=100)
    monitor.record_success("p")
    monitor.record_failure("p")
    monitor.record_success("p")  # reset consecutive
    monitor.record_failure("p")  # window: T,F,T,F -> 0.5, not < 0.5
    assert not monitor.is_quarantined("p")
    monitor.record_failure("p")  # window: F,T,F,F -> 0.25 < 0.5
    assert monitor.is_quarantined("p")


def test_success_heals_quarantine():
    monitor = NodeHealthMonitor(max_consecutive_failures=2)
    monitor.record_failure("p")
    monitor.record_failure("p")
    assert monitor.is_quarantined("p")
    # One success resets the consecutive count but the window score
    # (1/3) is still below threshold — healing is gradual, not instant.
    monitor.record_success("p")
    assert monitor.stats("p")["consecutive_failures"] == 0
    # Enough successes climb back above the threshold.
    for _ in range(4):
        monitor.record_success("p")
    assert not monitor.is_quarantined("p")
    assert monitor.score("p") > 0.5


def test_reset_forgets_peer():
    monitor = NodeHealthMonitor(max_consecutive_failures=1)
    monitor.record_failure("p")
    assert monitor.is_quarantined("p")
    monitor.reset("p")
    assert not monitor.is_quarantined("p")
    assert monitor.score("p") == 1.0


def test_stats_shape():
    monitor = NodeHealthMonitor()
    monitor.record_success("p")
    stats = monitor.stats("p")
    assert stats["samples"] == 1
    assert stats["total_successes"] == 1
    assert stats["consecutive_failures"] == 0
    assert monitor.stats("unknown")["samples"] == 0


def test_rejects_bad_config():
    with pytest.raises(SpecError):
        NodeHealthMonitor(window=0)
    with pytest.raises(SpecError):
        NodeHealthMonitor(quarantine_threshold=2.0)
    with pytest.raises(SpecError):
        NodeHealthMonitor(max_consecutive_failures=0)


def test_threshold_constant():
    assert DEFAULT_QUARANTINE_THRESHOLD == 0.5


def test_peer_health_dataclass_defaults():
    assert PeerHealth().consecutive_failures == 0


# --- node integration ---------------------------------------------------------------

def test_decide_remote_feeds_health(spec):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = PeerRecord(node_id=node_b.node_id, host="h", port=1)
    policy = DecisionPolicy(remote_inference=True)
    assert node_a.health.score(peer.node_id) == 1.0
    node_a.decide_remote(peer, spec, {"text": "a"}, policy=policy)
    stats = node_a.health.stats(peer.node_id)
    assert stats["total_successes"] == 1
    assert stats["score"] == 1.0


def test_decide_remote_failure_counts(spec):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b, fail=True)))
    peer = PeerRecord(node_id=node_b.node_id, host="h", port=1)
    policy = DecisionPolicy(remote_inference=True)
    with pytest.raises(BackendError):
        node_a.decide_remote(peer, spec, {"text": "a"}, policy=policy)
    stats = node_a.health.stats(peer.node_id)
    assert stats["total_failures"] == 1
    assert stats["consecutive_failures"] == 1


def test_refresh_scores_sinks_sick_peer(spec):
    node_a = _node("a")
    sick, healthy = _node("sick"), _node("healthy")
    peers = [PeerRecord(node_id=sick.node_id, host="h", port=1,
                        capabilities=sick.capabilities()),
             PeerRecord(node_id=healthy.node_id, host="h", port=2,
                        capabilities=healthy.capabilities())]
    node_a.discovery.add_adapter(_Static(peers))
    for _ in range(10):
        node_a.health.record_failure(sick.node_id)
    node_a.refresh_scores()
    ordered = [c.node_id for c in node_a.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    # local first (1.0), then healthy, sick last with 0.0 health
    assert ordered[-1] == sick.node_id
    assert ordered[1] == healthy.node_id
    assert node_a.router.scores_for(sick.node_id).health == 0.0
