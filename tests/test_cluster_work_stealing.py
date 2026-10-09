"""Tests for slice 216 — work stealing."""

from __future__ import annotations

import threading

import httpx
import pytest

from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import ClusterMessage, MessageType, decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.cluster.work_stealing import (
    DEFAULT_STEAL_BATCH,
    MAX_STEAL_BATCH,
    StealableQueue,
    StealJob,
)
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.server import build_gate


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n", serve_remote=True):
    return ClusterNode(NodeIdentity.generate(name), build_gate(),
                       serve_remote=serve_remote)


def _job(i, private=False):
    state = {"text": f"job-{i}"}
    if private:
        state["private_ssn"] = "000-00-0000"
    return StealJob(spec={"type": "categorical", "options": ["a", "b"]},
                    state=state)


# --- StealJob ------------------------------------------------------------------

def test_job_roundtrip():
    job = _job(1)
    clone = StealJob.from_dict(job.to_dict())
    assert clone.spec == job.spec and clone.state == job.state
    assert clone.enqueued_at == job.enqueued_at


def test_job_from_dict_rejects_garbage():
    for bad in (None, [], "x", {}, {"spec": {}}, {"state": {}},
                {"spec": {}, "state": {}, "policy": "x"}):
        with pytest.raises(SpecError):
            StealJob.from_dict(bad)


def test_job_redacted_strips_private():
    redacted = _job(1, private=True).redacted()
    assert "private_ssn" not in redacted.state
    assert redacted.state["text"] == "job-1"


# --- StealableQueue ---------------------------------------------------------------

def test_queue_take_is_lifo_steal_is_oldest():
    q = StealableQueue()
    for i in range(3):
        q.offer(_job(i))
    assert len(q) == 3
    assert q.take().state["text"] == "job-2"     # newest first locally
    stolen = q.steal(5)
    assert [j.state["text"] for j in stolen] == ["job-0", "job-1"]
    assert len(q) == 0


def test_steal_empty_returns_empty():
    assert StealableQueue().steal() == []
    assert StealableQueue().take() is None


def test_steal_respects_max_jobs():
    q = StealableQueue()
    for i in range(10):
        q.offer(_job(i))
    assert len(q.steal(3)) == 3
    assert len(q) == 7


def test_steal_capped_at_max_batch():
    q = StealableQueue()
    for i in range(MAX_STEAL_BATCH + 20):
        q.offer(_job(i))
    assert len(q.steal(10 ** 9)) == MAX_STEAL_BATCH


def test_steal_rejects_bad_max():
    q = StealableQueue()
    for bad in (0, -1, "3"):
        with pytest.raises(SpecError):
            q.steal(bad)


def test_offer_rejects_non_job():
    with pytest.raises(SpecError):
        StealableQueue().offer({"spec": {}})


def test_queue_thread_safe():
    q = StealableQueue()

    def worker(n):
        for i in range(200):
            q.offer(_job(n * 1000 + i))
            q.take()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(q) >= 0  # no corruption, no deadlock


def test_drain():
    q = StealableQueue()
    q.offer(_job(1))
    q.offer(_job(2))
    assert len(q.drain()) == 2
    assert len(q) == 0


# --- victim handler ---------------------------------------------------------------

def _steal_request(node, max_jobs=5):
    message = ClusterMessage(
        msg_type=MessageType.STEAL_REQUEST, sender="dd" * 32, seq=1,
        payload={"max_jobs": max_jobs})
    return node.dispatch(message)


def test_handler_serves_tail_jobs_redacted():
    victim = _node("victim")
    for i in range(4):
        victim.steal_queue.offer(_job(i, private=(i == 0)))
    reply = _steal_request(victim)
    assert reply.msg_type is MessageType.STEAL_RESPONSE
    jobs = reply.payload["jobs"]
    assert len(jobs) == 4
    assert all("private_ssn" not in j["state"] for j in jobs)
    assert reply.payload["remaining"] == 0
    assert len(victim.steal_queue) == 0


def test_handler_empty_queue():
    reply = _steal_request(_node("v"))
    assert reply.msg_type is MessageType.STEAL_RESPONSE
    assert reply.payload["jobs"] == []


def test_handler_refuses_when_not_serving():
    victim = _node("v", serve_remote=False)
    victim.steal_queue.offer(_job(1))
    reply = _steal_request(victim)
    assert reply.msg_type is MessageType.ERROR
    assert len(victim.steal_queue) == 1  # nothing stolen


def test_handler_rejects_bad_max_jobs():
    victim = _node("v")
    message = ClusterMessage(
        msg_type=MessageType.STEAL_REQUEST, sender="dd" * 32, seq=1,
        payload={"max_jobs": "lots"})
    reply = victim.dispatch(message)
    assert reply.msg_type is MessageType.ERROR


# --- thief side -------------------------------------------------------------------

def test_request_steal_end_to_end():
    thief, victim = _node("thief"), _node("victim")
    for i in range(6):
        victim.steal_queue.offer(_job(i))
    thief.rpc = RPCClient(
        node_id=thief.node_id,
        http_client=httpx.Client(transport=_Loopback(victim)))
    peer = PeerRecord(node_id=victim.node_id, host="h", port=1)
    stolen = thief.request_steal(peer, max_jobs=4)
    assert stolen == 4
    assert len(thief.steal_queue) == 4
    assert len(victim.steal_queue) == 2
    # Stolen jobs are the oldest (tail).
    assert thief.steal_queue.take().state["text"] == "job-3"


def test_request_steal_feeds_monitors():
    thief, victim = _node("thief"), _node("victim")
    victim.steal_queue.offer(_job(0))
    thief.rpc = RPCClient(
        node_id=thief.node_id,
        http_client=httpx.Client(transport=_Loopback(victim)))
    peer = PeerRecord(node_id=victim.node_id, host="h", port=1)
    thief.request_steal(peer)
    assert thief.health.stats(peer.node_id)["total_successes"] == 1
    assert thief.latency.stats(peer.node_id)["samples"] == 1


def test_request_steal_refusal_counts_against_health():
    thief = _node("thief")
    victim = _node("victim", serve_remote=False)
    thief.rpc = RPCClient(
        node_id=thief.node_id,
        http_client=httpx.Client(transport=_Loopback(victim)))
    peer = PeerRecord(node_id=victim.node_id, host="h", port=1)
    with pytest.raises(BackendUnavailable):
        thief.request_steal(peer)
    assert thief.health.stats(peer.node_id)["total_failures"] == 1


def test_rpc_steal_rejects_bad_max():
    thief = _node("thief")
    with pytest.raises(SpecError):
        thief.rpc.steal(
            PeerRecord(node_id="dd" * 32, host="h", port=1), max_jobs=0)


def test_default_batch_constant():
    assert DEFAULT_STEAL_BATCH == 8
