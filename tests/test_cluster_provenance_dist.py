"""Tests for slice 221 — distributed provenance."""

from __future__ import annotations

import time

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import ClusterMessage, MessageType, decode_message
from hugrgate.cluster.provenance_dist import (
    DEFAULT_PROVENANCE_PULL_LIMIT,
    MAX_PROVENANCE_PULL_LIMIT,
    ProvenanceExchange,
    attribute_record,
)
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import BackendError, SpecError
from hugrgate.provenance import DecisionRecord
from hugrgate.server import build_gate


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _peer(node):
    return PeerRecord(node_id=node.node_id, host="h", port=1,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _decide(node, spec, text="a"):
    return node.gate.decide(
        {"text": text}, spec,
        policy=DecisionPolicy(remote_inference=True))


# --- attribution -----------------------------------------------------------------

def test_attribute_record_sets_but_never_overwrites(spec):
    record = DecisionRecord.from_decision(
        {"text": "a"}, spec,
        _decide(_node(), spec))
    assert "node_id" not in record.metadata
    attribute_record(record, "aa" * 32)
    assert record.metadata["node_id"] == "aa" * 32
    attribute_record(record, "bb" * 32)
    assert record.metadata["node_id"] == "aa" * 32  # origin kept


# --- serve_pull ------------------------------------------------------------------

def test_serve_pull_attributes_and_limits(spec):
    node = _node()
    for i in range(5):
        _decide(node, spec, text=f"r{i}")
    dicts = node.provenance_exchange.serve_pull(None, 3)
    assert len(dicts) == 3
    assert all(d["metadata"]["node_id"] == node.node_id for d in dicts)


def test_serve_pull_since_filter(spec):
    node = _node()
    _decide(node, spec, text="old")
    cutoff = time.time()
    time.sleep(0.01)
    _decide(node, spec, text="new")
    dicts = node.provenance_exchange.serve_pull(cutoff, 100)
    assert len(dicts) == 1


def test_serve_pull_rejects_bad_args():
    exchange = ProvenanceExchange(_node())
    with pytest.raises(SpecError):
        exchange.serve_pull(None, 0)
    with pytest.raises(SpecError):
        exchange.serve_pull(-1.0, 10)
    with pytest.raises(SpecError):
        exchange.serve_pull("yesterday", 10)


def test_serve_pull_clamps_limit(spec):
    node = _node()
    _decide(node, spec)
    dicts = node.provenance_exchange.serve_pull(
        None, MAX_PROVENANCE_PULL_LIMIT + 5000)
    assert len(dicts) == 1  # clamped, not exploded


def test_handler_serves_pull(spec):
    node = _node()
    _decide(node, spec)
    message = ClusterMessage(
        msg_type=MessageType.PROVENANCE_PULL, sender="dd" * 32, seq=1,
        payload={"since": None, "limit": 10})
    reply = node.dispatch(message)
    assert reply.msg_type is MessageType.PROVENANCE_RESPONSE
    assert len(reply.payload["records"]) == 1
    assert reply.payload["node_id"] == node.node_id


def test_handler_rejects_bad_limit():
    node = _node()
    message = ClusterMessage(
        msg_type=MessageType.PROVENANCE_PULL, sender="dd" * 32, seq=1,
        payload={"limit": "many"})
    reply = node.dispatch(message)
    assert reply.msg_type is MessageType.ERROR


# --- pull + merge ------------------------------------------------------------------

def test_pull_and_merge_end_to_end(spec):
    node_a, node_b = _node("a"), _node("b")
    for i in range(3):
        _decide(node_b, spec, text=f"b{i}")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = _peer(node_b)
    added = node_a.provenance_exchange.pull_and_merge(peer)
    assert added == 3
    assert node_a.gate.provenance.count() == 3
    # Idempotent: pulling again merges nothing.
    assert node_a.provenance_exchange.pull_and_merge(peer) == 0
    assert node_a.gate.provenance.count() == 3
    # Merged records keep their true origin...
    origins = {r.metadata["node_id"]
               for r in node_a.gate.provenance.recent(10)}
    assert origins == {node_b.node_id}
    # ...and the local chain still verifies.
    assert node_a.gate.provenance.verify_chain()


def test_merge_keeps_local_records_distinct(spec):
    node_a, node_b = _node("a"), _node("b")
    _decide(node_a, spec, text="same")
    _decide(node_b, spec, text="same")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    added = node_a.provenance_exchange.pull_and_merge(_peer(node_b))
    assert added == 1  # same request hash, different node -> kept
    assert node_a.gate.provenance.count() == 2


def test_merge_rejects_non_records():
    with pytest.raises(SpecError):
        ProvenanceExchange(_node()).merge([{"not": "a record"}])


def test_pull_validates_record_shapes():
    node_a, node_b = _node("a"), _node("b")

    class _Liar(httpx.BaseTransport):
        def handle_request(self, request):
            message = decode_message(request.content)
            reply = node_b._respond(
                message, MessageType.PROVENANCE_RESPONSE,
                {"records": [{"bogus": True}]})
            return httpx.Response(
                200, json={"envelope": reply.to_dict()})

    node_a.rpc = RPCClient(
        node_id=node_a.node_id, http_client=httpx.Client(transport=_Liar()))
    with pytest.raises(SpecError):
        node_a.provenance_exchange.pull(_peer(node_b))


def test_pull_rejects_bad_limit():
    with pytest.raises(SpecError):
        ProvenanceExchange(_node()).pull(
            PeerRecord(node_id="dd" * 32, host="h", port=1), limit=0)


def test_rpc_pull_provenance_rejects_bad_limit():
    node = _node()
    with pytest.raises(SpecError):
        node.rpc.pull_provenance(
            PeerRecord(node_id="dd" * 32, host="h", port=1), limit=-2)


def test_pull_unexpected_reply():
    node_a = _node("a")

    class _Weird(httpx.BaseTransport):
        def handle_request(self, request):
            decode_message(request.content)  # must still decode
            reply = ClusterMessage(
                msg_type=MessageType.HEARTBEAT, sender="dd" * 32, seq=2,
                payload={})
            return httpx.Response(
                200, json={"envelope": reply.to_dict()})

    node_a.rpc = RPCClient(
        node_id=node_a.node_id, http_client=httpx.Client(transport=_Weird()))
    with pytest.raises(BackendError, match="unexpected"):
        node_a.rpc.pull_provenance(
            PeerRecord(node_id="dd" * 32, host="h", port=1))


def test_constants():
    assert DEFAULT_PROVENANCE_PULL_LIMIT == 100
    assert MAX_PROVENANCE_PULL_LIMIT == 1000
