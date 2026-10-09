"""Tests for slice 214 — node latency scoring."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.node_latency import (
    DEFAULT_LATENCY_TARGET_MS,
    LatencyTracker,
    PeerLatency,
)
from hugrgate.cluster.protocol import decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import SpecError
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

    def handle_request(self, request):
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- tracker unit --------------------------------------------------------------------

def test_unknown_peer_scores_perfect():
    assert LatencyTracker().score("new") == 1.0


def test_at_or_under_target_scores_perfect():
    tracker = LatencyTracker(target_ms=250.0)
    tracker.record("p", 100.0)
    tracker.record("p", 250.0)
    assert tracker.score("p") == 1.0


def test_slower_peer_scores_fraction():
    tracker = LatencyTracker(target_ms=100.0, alpha=1.0)
    tracker.record("p", 400.0)
    assert tracker.score("p") == pytest.approx(0.25)


def test_ewma_weights_recent_samples():
    tracker = LatencyTracker(alpha=0.5)
    tracker.record("p", 100.0)
    assert tracker.ewma("p") == pytest.approx(100.0)
    tracker.record("p", 200.0)
    assert tracker.ewma("p") == pytest.approx(150.0)


def test_percentiles():
    tracker = LatencyTracker()
    for v in (10.0, 20.0, 30.0, 40.0):
        tracker.record("p", v)
    assert tracker.percentile("p", 0.5) == pytest.approx(20.0)
    assert tracker.percentile("p", 0.95) == pytest.approx(40.0)
    assert tracker.percentile("new", 0.5) == 0.0


def test_window_bounds_memory():
    tracker = LatencyTracker(window=5)
    for i in range(20):
        tracker.record("p", float(i))
    assert tracker.stats("p")["samples"] == 5


def test_record_rejects_bad_samples():
    tracker = LatencyTracker()
    for bad in (-1.0, float("inf"), float("nan"), "x"):
        with pytest.raises(SpecError):
            tracker.record("p", bad)


def test_rejects_bad_config():
    with pytest.raises(SpecError):
        LatencyTracker(target_ms=0)
    with pytest.raises(SpecError):
        LatencyTracker(alpha=0.0)
    with pytest.raises(SpecError):
        LatencyTracker(window=0)
    with pytest.raises(SpecError):
        LatencyTracker().percentile("p", 1.5)


def test_reset_forgets_peer():
    tracker = LatencyTracker(target_ms=10.0, alpha=1.0)
    tracker.record("p", 1000.0)
    assert tracker.score("p") < 1.0
    tracker.reset("p")
    assert tracker.score("p") == 1.0


def test_stats_shape():
    tracker = LatencyTracker()
    tracker.record("p", 50.0)
    stats = tracker.stats("p")
    assert stats["samples"] == 1
    assert stats["ewma_ms"] == pytest.approx(50.0)
    assert stats["score"] == 1.0
    assert tracker.stats("new")["samples"] == 0


def test_target_constant():
    assert DEFAULT_LATENCY_TARGET_MS == 250.0


def test_peer_latency_defaults():
    assert PeerLatency().count == 0


# --- node integration -------------------------------------------------------------------

def test_decide_remote_records_latency(spec):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = PeerRecord(node_id=node_b.node_id, host="h", port=1)
    node_a.decide_remote(peer, spec, {"text": "a"},
                         policy=DecisionPolicy(remote_inference=True))
    stats = node_a.latency.stats(peer.node_id)
    assert stats["samples"] == 1
    assert stats["ewma_ms"] >= 0.0


def test_refresh_scores_carries_latency(spec):
    node_a = _node("a")
    fast, slow = _node("fast"), _node("slow")
    peers = [PeerRecord(node_id=fast.node_id, host="h", port=1,
                        capabilities=fast.capabilities()),
             PeerRecord(node_id=slow.node_id, host="h", port=2,
                        capabilities=slow.capabilities())]
    node_a.discovery.add_adapter(_Static(peers))
    node_a.latency.record(fast.node_id, 10.0)
    node_a.latency.record(slow.node_id, 2000.0)
    node_a.refresh_scores()
    assert node_a.router.scores_for(fast.node_id).latency == 1.0
    slow_score = node_a.router.scores_for(slow.node_id).latency
    assert slow_score == pytest.approx(250.0 / 2000.0)
    ordered = [c.node_id for c in node_a.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert ordered[1] == fast.node_id
    assert ordered[2] == slow.node_id
