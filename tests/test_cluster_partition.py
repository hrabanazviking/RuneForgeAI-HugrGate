"""Tests for slice 219 — network partition handling."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.partition import (
    DEFAULT_PARTITION_STALE_AFTER_S,
    PartitionDetector,
)
from hugrgate.cluster.protocol import ClusterMessage, MessageType, decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import BackendUnavailable, SpecError
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


def _node(name="n", enforce_quorum=False):
    return ClusterNode(NodeIdentity.generate(name), build_gate(),
                       enforce_quorum=enforce_quorum)


def _peer(node, port=1):
    return PeerRecord(node_id=node.node_id, host="h", port=port,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- detector unit -----------------------------------------------------------------

def test_rejects_bad_config():
    with pytest.raises(SpecError):
        PartitionDetector(stale_after_s=0)


def test_lone_node_is_its_own_majority():
    detector = PartitionDetector()
    assert detector.has_quorum([])


def test_unknown_peer_is_dark():
    detector = PartitionDetector()
    assert not detector.is_live("aa" * 32)
    assert detector.last_seen("aa" * 32) is None
    assert not detector.has_quorum(["aa" * 32])


def test_heartbeat_makes_peer_live():
    clock = _Clock()
    detector = PartitionDetector(stale_after_s=10.0, clock=clock)
    detector.note_heartbeat("aa" * 32)
    assert detector.is_live("aa" * 32)
    assert detector.last_seen("aa" * 32) == 1000.0
    assert detector.has_quorum(["aa" * 32])  # 2/2 alive


def test_stale_peer_is_dark():
    clock = _Clock()
    detector = PartitionDetector(stale_after_s=10.0, clock=clock)
    detector.note_heartbeat("aa" * 32)
    clock.now += 11.0
    assert not detector.is_live("aa" * 32)
    assert not detector.has_quorum(["aa" * 32])  # 1/2 alive


def test_quorum_math():
    clock = _Clock()
    detector = PartitionDetector(stale_after_s=10.0, clock=clock)
    peers = [f"{i:02x}" * 32 for i in range(4)]
    for pid in peers[:3]:
        detector.note_heartbeat(pid)
    # 4/5 alive -> quorum.
    assert detector.has_quorum(peers)
    assert detector.live_peers(peers) == peers[:3]
    clock.now += 11.0
    # 1/5 alive -> partitioned.
    assert not detector.has_quorum(peers)
    # Exactly half is not a majority: 2 nodes, peer dark -> 1/2.
    detector2 = PartitionDetector(stale_after_s=10.0, clock=_Clock())
    assert not detector2.has_quorum(["aa" * 32])


def test_forget():
    detector = PartitionDetector()
    detector.note_heartbeat("aa" * 32)
    detector.forget("aa" * 32)
    assert not detector.is_live("aa" * 32)


def test_stale_constant():
    assert DEFAULT_PARTITION_STALE_AFTER_S == 30.0


# --- node integration ------------------------------------------------------------------

def _decide_message(spec):
    return ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="dd" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"text": "a"},
                 "policy": DecisionPolicy(
                     remote_inference=True).to_dict()})


def test_heartbeat_handler_records_liveness():
    node = _node()
    message = ClusterMessage(msg_type=MessageType.HEARTBEAT,
                             sender="dd" * 32, seq=1, payload={})
    reply = node.dispatch(message)
    assert reply.msg_type is MessageType.HEARTBEAT
    assert reply.payload["alive"] is True
    assert node.partition.is_live("dd" * 32)


def test_in_quorum_reflects_heartbeats():
    node = _node(enforce_quorum=True)
    peer_node = _node("peer")
    node.discovery.add_adapter(_Static([_peer(peer_node)]))
    assert not node.in_quorum()  # peer dark
    node.partition.note_heartbeat(peer_node.node_id)
    assert node.in_quorum()


def test_partitioned_node_refuses_inbound_work(spec):
    node = _node(enforce_quorum=True)
    peer_node = _node("peer")
    node.discovery.add_adapter(_Static([_peer(peer_node)]))
    reply = node.dispatch(_decide_message(spec))
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "backend_unavailable"
    assert "no quorum" in reply.payload["error"]["message"]
    # A heartbeat revives it.
    node.partition.note_heartbeat(peer_node.node_id)
    reply = node.dispatch(_decide_message(spec))
    assert reply.msg_type is not MessageType.ERROR


def test_partitioned_node_routes_local_only(spec):
    node = _node(enforce_quorum=True)
    peer_node = _node("peer")
    node.discovery.add_adapter(_Static([_peer(peer_node)]))
    kinds = [c.kind for c in node.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert kinds == ["local"]
    node.partition.note_heartbeat(peer_node.node_id)
    kinds = [c.kind for c in node.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert kinds == ["local", "remote"]


def test_partitioned_node_refuses_decide_remote(spec):
    node = _node(enforce_quorum=True)
    peer_node = _node("peer")
    node.discovery.add_adapter(_Static([_peer(peer_node)]))
    with pytest.raises(BackendUnavailable, match="no quorum"):
        node.decide_remote(_peer(peer_node), spec, {"text": "a"},
                           policy=DecisionPolicy(remote_inference=True))


def test_quorum_not_enforced_by_default(spec):
    node = _node()  # enforce_quorum=False
    peer_node = _node("peer")
    node.discovery.add_adapter(_Static([_peer(peer_node)]))
    assert not node.in_quorum()
    kinds = [c.kind for c in node.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert kinds == ["local", "remote"]  # still routes
    reply = node.dispatch(_decide_message(spec))
    assert reply.msg_type is not MessageType.ERROR


def test_ping_end_to_end():
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = _peer(node_b)
    payload = node_a.ping(peer)
    assert payload["alive"] is True
    assert payload["node_id"] == node_b.node_id
    assert node_a.partition.is_live(node_b.node_id)
    assert node_a.in_quorum()
