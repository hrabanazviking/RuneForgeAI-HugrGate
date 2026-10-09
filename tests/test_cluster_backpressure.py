"""Tests for slice 218 — backpressure protocol."""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.backpressure import (
    DEFAULT_ADMISSION_CAPACITY,
    DEFAULT_ADMISSION_REFILL_PER_SECOND,
    WORK_MESSAGE_TYPES,
    AdmissionController,
)
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import ClusterMessage, MessageType
from hugrgate.cluster.routes import build_cluster_router
from hugrgate.errors import QueueFull, SpecError
from hugrgate.server import build_gate


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _message(msg_type, payload=None):
    return ClusterMessage(
        msg_type=msg_type, sender="dd" * 32, seq=1,
        payload=payload or {})


# --- AdmissionController unit ---------------------------------------------------

def test_fresh_controller_admits():
    controller = AdmissionController(capacity=4, refill_per_second=1000.0)
    assert all(controller.try_acquire() for _ in range(4))
    assert not controller.try_acquire()
    assert controller.stats()["admitted"] == 4
    assert controller.stats()["refused"] == 1


def test_tokens_refill_over_time():
    controller = AdmissionController(capacity=1, refill_per_second=50.0)
    assert controller.try_acquire()
    assert not controller.try_acquire()
    time.sleep(0.03)  # ~1.5 tokens at 50/s
    assert controller.try_acquire()


def test_retry_after_hint():
    controller = AdmissionController(capacity=1, refill_per_second=10.0)
    controller.try_acquire()
    wait = controller.retry_after_ms()
    assert 0 < wait <= 100.0
    fresh = AdmissionController()
    assert fresh.retry_after_ms() == 0.0


def test_rejects_bad_config():
    with pytest.raises(SpecError):
        AdmissionController(capacity=0)
    with pytest.raises(SpecError):
        AdmissionController(refill_per_second=0)


def test_constants():
    assert DEFAULT_ADMISSION_CAPACITY == 128
    assert DEFAULT_ADMISSION_REFILL_PER_SECOND == 64.0
    assert WORK_MESSAGE_TYPES == {"decide_request", "batch_request",
                                  "steal_request"}


# --- node dispatch ---------------------------------------------------------------

def _decide_payload():
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    return {"spec": spec.to_dict(), "state": {"text": "a"},
            "policy": DecisionPolicy(remote_inference=True).to_dict()}


def test_work_messages_shed_under_load():
    node = _node()
    node.admission = AdmissionController(capacity=2,
                                         refill_per_second=0.01)
    ok = _node()  # sanity: payload itself is fine
    assert ok.dispatch(_message(MessageType.DECIDE_REQUEST,
                                _decide_payload())).msg_type is not \
        MessageType.ERROR
    for _ in range(2):
        node.dispatch(_message(MessageType.DECIDE_REQUEST,
                               _decide_payload()))
    reply = node.dispatch(_message(MessageType.DECIDE_REQUEST,
                                   _decide_payload()))
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "queue_full"
    assert reply.payload["error"]["recoverable"] is True
    assert reply.payload["error"]["details"]["retry_after_ms"] > 0


def test_control_plane_never_shed():
    node = _node()
    node.admission = AdmissionController(capacity=1,
                                         refill_per_second=0.01)
    node.dispatch(_message(MessageType.DECIDE_REQUEST, _decide_payload()))
    # Policy pull (control plane) still gets through with zero tokens.
    reply = node.dispatch(_message(MessageType.POLICY_PULL, {}))
    error = reply.payload.get("error", {})
    assert not (reply.msg_type is MessageType.ERROR
                and error.get("code") == "queue_full")


def test_shed_load_recovers():
    node = _node()
    node.admission = AdmissionController(capacity=1,
                                         refill_per_second=1000.0)
    node.dispatch(_message(MessageType.DECIDE_REQUEST, _decide_payload()))
    assert node.dispatch(
        _message(MessageType.DECIDE_REQUEST,
                 _decide_payload())).msg_type is MessageType.ERROR
    time.sleep(0.05)
    reply = node.dispatch(_message(MessageType.DECIDE_REQUEST,
                                   _decide_payload()))
    assert reply.msg_type is not MessageType.ERROR


# --- HTTP 429 mapping ---------------------------------------------------------------

def test_route_maps_queue_full_to_429():
    node = _node()
    node.admission = AdmissionController(capacity=0 + 1,
                                         refill_per_second=0.01)
    node.dispatch(_message(MessageType.DECIDE_REQUEST, _decide_payload()))
    app_router = build_cluster_router(node)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(app_router)
    client = TestClient(app)
    from hugrgate.cluster.protocol import encode_message
    body = encode_message(_message(MessageType.DECIDE_REQUEST,
                                   _decide_payload()))
    response = client.post("/cluster/rpc", content=body)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) >= 1
    envelope = response.json()["envelope"]
    assert envelope["payload"]["error"]["code"] == "queue_full"


def test_route_healthy_node_stays_200():
    node = _node()
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(build_cluster_router(node))
    client = TestClient(app)
    from hugrgate.cluster.protocol import encode_message
    body = encode_message(_message(MessageType.HEARTBEAT, {}))
    assert client.post("/cluster/rpc", content=body).status_code == 200


def test_rpc_client_turns_429_into_queue_full():
    from hugrgate.cluster.discovery import PeerRecord
    from hugrgate.cluster.protocol import new_trace_id
    from hugrgate.cluster.rpc import RPCClient, error_envelope
    from hugrgate.errors import HugrGateError

    node = _node()

    class _429(httpx.BaseTransport):
        def handle_request(self, request):
            err = error_envelope(
                QueueFull("shedding", retry_after_ms=500.0),
                node.node_id, 1, new_trace_id()).payload["error"]
            return httpx.Response(
                429, headers={"Retry-After": "1"},
                json={"envelope": {"payload": {"error": err}}})

    client = RPCClient(
        node_id="ee" * 32,
        http_client=httpx.Client(transport=_429()))
    peer = PeerRecord(node_id=node.node_id, host="h", port=1)
    with pytest.raises(QueueFull) as exc_info:
        client.send(peer, _message(MessageType.HEARTBEAT, {}))
    assert exc_info.value.recoverable is True
    assert HugrGateError.from_dict(
        {"code": "queue_full"}).code == "queue_full"
