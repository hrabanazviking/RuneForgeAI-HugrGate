"""Tests for slice 217 — distributed batching."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.distributed_batch import (
    DEFAULT_MAX_BATCH_SIZE,
    BatchJob,
    BatchOutcome,
    DistributedBatcher,
)
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
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
        self.calls = 0

    def handle_request(self, request):
        self.calls += 1
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


class _Multi(httpx.BaseTransport):
    """Route by destination port; port 1 is always down."""

    def __init__(self, nodes):
        self.nodes = nodes  # port -> ClusterNode
        self.calls = {port: 0 for port in nodes}

    def handle_request(self, request):
        port = request.url.port
        self.calls[port] += 1
        if port == 1:
            raise httpx.ConnectError("down")
        reply = self.nodes[port].dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _wire(caller, peer_node, transport=None):
    transport = transport or _Loopback(peer_node)
    caller.rpc = RPCClient(
        node_id=caller.node_id,
        http_client=httpx.Client(transport=transport))
    return transport


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _job(spec, i):
    return BatchJob(spec=spec, state={"text": f"job-{i}"},
                    policy=DecisionPolicy(remote_inference=True))


# --- unit --------------------------------------------------------------------

def test_submit_validates():
    batcher = DistributedBatcher(_node())
    with pytest.raises(SpecError):
        batcher.submit("x", {"not": "a job"})
    with pytest.raises(SpecError):
        batcher.submit("x", BatchJob(spec="nope", state={}))
    with pytest.raises(SpecError):
        DistributedBatcher(_node(), max_batch_size=0)


def test_pending_counts(spec):
    batcher = DistributedBatcher(_node())
    batcher.submit("a", _job(spec, 1))
    batcher.submit("a", _job(spec, 2))
    batcher.submit("b", _job(spec, 3))
    assert batcher.pending("a") == 2
    assert batcher.pending() == 3
    assert batcher.max_batch_size == DEFAULT_MAX_BATCH_SIZE


def test_flush_empty(spec):
    assert DistributedBatcher(_node()).flush() == {}


def test_outcome_defaults():
    outcome = BatchOutcome(ok=True)
    assert outcome.result is None and not outcome.abstained


# --- integration ---------------------------------------------------------------

def test_flush_groups_by_peer_one_envelope_each(spec):
    caller = _node("caller")
    peer_b, peer_c = _node("b"), _node("c")
    transport = _Multi({2: peer_b, 3: peer_c})
    caller.rpc = RPCClient(
        node_id=caller.node_id, http_client=httpx.Client(transport=transport))
    caller.discovery.add_adapter(_Static([
        PeerRecord(node_id=peer_b.node_id, host="h", port=2),
        PeerRecord(node_id=peer_c.node_id, host="h", port=3),
    ]))
    for i in range(3):
        caller.batcher.submit(peer_b.node_id, _job(spec, i))
    for i in range(2):
        caller.batcher.submit(peer_c.node_id, _job(spec, i))
    outcomes = caller.batcher.flush()
    assert set(outcomes) == {peer_b.node_id, peer_c.node_id}
    assert [o.ok for o in outcomes[peer_b.node_id]] == [True] * 3
    assert [o.ok for o in outcomes[peer_c.node_id]] == [True] * 2
    # One envelope per peer, not one per job.
    assert transport.calls[2] == 1
    assert transport.calls[3] == 1
    assert caller.batcher.pending() == 0
    for outcome in outcomes[peer_b.node_id]:
        assert outcome.result.value in ("a", "b")


def test_flush_chunks_at_max_batch_size(spec):
    caller = _node("caller")
    peer_node = _node("b")
    transport = _wire(caller, peer_node)
    caller.discovery.add_adapter(_Static([
        PeerRecord(node_id=peer_node.node_id, host="h", port=1)]))
    caller.batcher = DistributedBatcher(caller, max_batch_size=4)
    for i in range(10):
        caller.batcher.submit(peer_node.node_id, _job(spec, i))
    outcomes = caller.batcher.flush()
    assert len(outcomes[peer_node.node_id]) == 10
    assert all(o.ok for o in outcomes[peer_node.node_id])
    assert transport.calls == 3  # 4 + 4 + 2


def test_flush_failed_peer_poisons_only_its_jobs(spec):
    caller = _node("caller")
    dead, live = _node("dead"), _node("live")
    transport = _Multi({1: dead, 2: live})  # port 1 always down
    caller.rpc = RPCClient(
        node_id=caller.node_id, http_client=httpx.Client(transport=transport))
    caller.discovery.add_adapter(_Static([
        PeerRecord(node_id=dead.node_id, host="h", port=1),
        PeerRecord(node_id=live.node_id, host="h", port=2),
    ]))
    caller.batcher.submit(dead.node_id, _job(spec, 1))
    caller.batcher.submit(live.node_id, _job(spec, 2))
    outcomes = caller.batcher.flush()
    assert not outcomes[dead.node_id][0].ok
    assert "unreachable" in outcomes[dead.node_id][0].error
    assert outcomes[live.node_id][0].ok
    # Buffers cleared even on failure.
    assert caller.batcher.pending() == 0


def test_flush_unknown_peer(spec):
    caller = _node("caller")
    caller.batcher.submit("ff" * 32, _job(spec, 1))
    outcomes = caller.batcher.flush()
    assert not outcomes["ff" * 32][0].ok
    assert "unknown peer" in outcomes["ff" * 32][0].error


def test_local_only_job_never_leaves_node(spec):
    caller = _node("caller")
    peer_node = _node("b")
    transport = _wire(caller, peer_node)
    caller.discovery.add_adapter(_Static([
        PeerRecord(node_id=peer_node.node_id, host="h", port=1)]))
    local_job = BatchJob(spec=spec, state={"text": "a"},
                         policy=DecisionPolicy())  # remote blocked
    caller.batcher.submit(peer_node.node_id, local_job)
    caller.batcher.submit(peer_node.node_id, _job(spec, 1))
    outcomes = caller.batcher.flush()
    pair = outcomes[peer_node.node_id]
    assert not pair[0].ok
    assert "remote inference blocked" in pair[0].error
    assert pair[1].ok  # the allowed job still went
    assert transport.calls == 1


def test_abstention_becomes_outcome(spec):
    caller = _node("caller")
    peer_node = _node("b")
    _wire(caller, peer_node)
    caller.discovery.add_adapter(_Static([
        PeerRecord(node_id=peer_node.node_id, host="h", port=1)]))
    job = BatchJob(
        spec=spec, state={"text": "zzz no match at all"},
        policy=DecisionPolicy(remote_inference=True,
                              minimum_probability=0.99))
    caller.batcher.submit(peer_node.node_id, job)
    outcomes = caller.batcher.flush()
    outcome = outcomes[peer_node.node_id][0]
    assert not outcome.ok and outcome.abstained
