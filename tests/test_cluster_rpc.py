"""Tests for slice 207 — remote decision RPC."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    ClusterMessage,
    MessageType,
    decode_message,
    encode_message,
)
from hugrgate.cluster.rpc import RemoteBackend, RPCClient, error_envelope
from hugrgate.daemon import DaemonConfig, create_daemon_app
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    PrivacyViolation,
    SpecError,
)
from hugrgate.serde import policy_to_dict
from hugrgate.server import build_gate, create_app


def _remote_policy(**kw):
    kw.setdefault("remote_inference", True)
    return DecisionPolicy(**kw)


@pytest.fixture
def server_node():
    return ClusterNode(NodeIdentity.generate("srv"), build_gate())


@pytest.fixture
def peer(server_node):
    return PeerRecord(node_id=server_node.node_id, host="testserver",
                      port=80)


class LoopbackTransport(httpx.BaseTransport):
    """In-process transport: envelopes go straight to node.dispatch.

    Exercises the full RPCClient path (encode, send, error mapping)
    with zero sockets.
    """

    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        try:
            message = decode_message(request.content)
        except SpecError as e:
            return httpx.Response(
                400, json={"error": {"code": "spec_error",
                                    "message": str(e)}})
        reply = self.node.dispatch(
            message,
            auth_tag=request.headers.get("x-cluster-mac"),
            raw=request.content)
        return httpx.Response(200, json={"envelope": reply.to_dict()})


@pytest.fixture
def rpc(server_node, peer):
    client = RPCClient(node_id=NodeIdentity.generate().node_id,
                       http_client=httpx.Client(
                           transport=LoopbackTransport(server_node)))
    yield client
    client.close()


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["ignore", "escalate"])


# --- decide round trip -------------------------------------------------------

def test_decide_round_trip(rpc, peer, spec, server_node):
    result = rpc.decide(peer, spec, {"text": "escalate now"},
                        policy=_remote_policy())
    assert result.value in ("ignore", "escalate")
    assert result.metadata["remote_node"] == server_node.node_id
    assert result.metadata["served_by"] == server_node.node_id
    assert "remote_trace_id" in result.metadata


def test_decide_traces_correlate_at_dispatch(server_node, spec):
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        trace_id="ee" * 16,
        payload={"spec": spec.to_dict(), "state": {"x": 1},
                 "policy": policy_to_dict(_remote_policy())})
    reply = server_node.dispatch(message)
    assert reply.trace_id == "ee" * 16
    assert reply.msg_type is MessageType.DECIDE_RESPONSE


def test_abstention_propagates(rpc, peer, spec):
    policy = _remote_policy(minimum_probability=0.99)
    with pytest.raises(Abstention):
        rpc.decide(peer, spec, {"text": "nothing matches here"}, policy)


def test_batch_round_trip(rpc, peer, spec):
    results = rpc.batch(peer, [
        {"spec": spec, "state": {"text": "escalate"}},
        {"spec": spec, "state": {"text": "ignore it"}},
    ], policy=_remote_policy())
    assert len(results) == 2
    assert all("result" in r for r in results)


def test_batch_item_error_isolated(rpc, peer, spec):
    results = rpc.batch(peer, [
        {"spec": spec, "state": {"text": "escalate"}},
        {"spec": {"type": "categorical", "options": ["only"]},
         "state": {}},
    ], policy=_remote_policy())
    assert "result" in results[0]
    assert results[1]["error"]["code"] == "spec_error"


# --- privacy: fail-closed both ends ------------------------------------------

def test_client_blocks_remote_without_policy_flag(rpc, peer, spec):
    with pytest.raises(PrivacyViolation, match="remote_inference"):
        rpc.decide(peer, spec, {"x": 1},
                   policy=DecisionPolicy())  # remote_inference=False


def test_server_rejects_remote_without_policy_flag(server_node, spec):
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"x": 1},
                 "policy": policy_to_dict(DecisionPolicy())})
    reply = server_node.dispatch(message)
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "privacy_violation"


def test_serve_remote_kill_switch(spec):
    node = ClusterNode(NodeIdentity.generate(), build_gate(),
                       serve_remote=False)
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"x": 1},
                 "policy": policy_to_dict(_remote_policy())})
    reply = node.dispatch(message)
    assert reply.payload["error"]["code"] == "backend_unavailable"


# --- error mapping ------------------------------------------------------------

def test_dispatch_bad_spec_envelope(server_node):
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        payload={"spec": {"type": "categorical", "options": ["solo"]},
                 "state": {}, "policy": policy_to_dict(_remote_policy())})
    reply = server_node.dispatch(message)
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "spec_error"


def test_unknown_message_type_gets_error_envelope(server_node):
    message = ClusterMessage(msg_type=MessageType.GOODBYE,
                             sender="ab" * 32, seq=1, payload={})
    reply = server_node.dispatch(message)
    assert reply.msg_type is MessageType.ERROR
    assert "unsupported message type" in reply.payload["error"]["message"]


def test_unreachable_peer_maps_to_backend_unavailable(spec):
    peer = PeerRecord(node_id="ab" * 32, host="127.0.0.1", port=59999)
    client = RPCClient(node_id=NodeIdentity.generate().node_id, timeout=1.0)
    try:
        with pytest.raises(BackendUnavailable, match="unreachable"):
            client.decide(peer, spec, {"x": 1},
                          policy=_remote_policy())
    finally:
        client.close()


def test_garbage_http_body_is_400(server_node):
    client = TestClient(create_app(node=server_node))
    r = client.post(CLUSTER_RPC_PATH, content=b"not json at all")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "spec_error"


def test_rpc_endpoint_missing_without_node():
    client = TestClient(create_app())
    r = client.get("/cluster/health")
    assert r.status_code == 404


def test_cluster_rpc_route_end_to_end(server_node, spec):
    """Full HTTP path: envelope bytes -> route -> node -> envelope."""
    client = TestClient(create_app(node=server_node))
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST,
        sender=NodeIdentity.generate().node_id, seq=1,
        payload={"spec": spec.to_dict(), "state": {"text": "escalate"},
                 "policy": policy_to_dict(_remote_policy())})
    r = client.post(CLUSTER_RPC_PATH, content=encode_message(message))
    assert r.status_code == 200
    reply = ClusterMessage.from_dict(r.json()["envelope"])
    assert reply.msg_type is MessageType.DECIDE_RESPONSE
    assert reply.payload["result"]["value"] in ("ignore", "escalate")


# --- hooks --------------------------------------------------------------------

def test_outbound_hook_applied(rpc, peer, spec):
    seen = []

    def hook(message):
        seen.append(message.msg_type)
        message.payload["signed"] = True
        return message

    rpc._outbound_hook = hook
    rpc.decide(peer, spec, {"x": 1}, policy=_remote_policy())
    assert seen == [MessageType.DECIDE_REQUEST]


def test_inbound_hook_can_reject(server_node, spec):
    from hugrgate.errors import PrivacyViolation as PV
    server_node.inbound_hook = lambda m: (_ for _ in ()).throw(
        PV("no entry"))
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"x": 1},
                 "policy": policy_to_dict(_remote_policy())})
    reply = server_node.dispatch(message)
    assert reply.payload["error"]["code"] == "privacy_violation"


def test_error_envelope_shape():
    env = error_envelope(SpecError("bad"), "ab" * 32, 3, "ee" * 16)
    assert env.msg_type is MessageType.ERROR
    assert env.payload["error"]["code"] == "spec_error"
    assert env.trace_id == "ee" * 16


# --- RemoteBackend --------------------------------------------------------------

def test_remote_backend_evaluate(rpc, peer, spec, server_node):
    peer_with_caps = PeerRecord(
        node_id=server_node.node_id, host="testserver", port=80,
        capabilities=server_node.capabilities())
    backend = RemoteBackend(peer_with_caps, rpc)
    assert backend.is_remote is True
    assert backend.name.startswith("remote@")
    assert "categorical" in backend.capabilities()["spec_types"]
    assert backend.supports(spec)
    result = backend.evaluate({"text": "escalate"}, spec)
    assert result.value in ("ignore", "escalate")


def test_remote_backend_without_caps_claims_all_types(rpc, peer):
    from hugrgate.spec import SPEC_TYPES
    backend = RemoteBackend(peer, rpc)
    assert backend.capabilities()["spec_types"] == list(SPEC_TYPES)
    assert backend.supports(DecisionSpec(type="numeric", minimum=0.0,
                                        maximum=1.0))


def test_remote_backend_in_core_gate(rpc, peer, spec, server_node):
    gate = HugrGate()
    gate.register(RemoteBackend(
        PeerRecord(node_id=server_node.node_id, host="testserver",
                   port=80,
                   capabilities=server_node.capabilities()), rpc))
    policy = _remote_policy(preferred_backends=[f"remote@{server_node.node_id[:12]}"])
    result = gate.decide({"text": "escalate"}, spec, policy)
    assert result.backend.startswith("remote@")
    assert result.value in ("ignore", "escalate")


def test_remote_backend_transport_failure_is_backend_error(spec):
    peer = PeerRecord(node_id="ab" * 32, host="127.0.0.1", port=59998)
    rpc = RPCClient(node_id=NodeIdentity.generate().node_id, timeout=1.0)
    backend = RemoteBackend(peer, rpc)
    try:
        with pytest.raises(BackendError):
            backend.evaluate({"x": 1}, spec)
    finally:
        rpc.close()


# --- routes ---------------------------------------------------------------------

def test_cluster_health_and_peers_endpoints(server_node):
    client = TestClient(create_app(node=server_node))
    health = client.get("/cluster/health").json()
    assert health["status"] == "ok"
    assert health["node_id"] == server_node.node_id
    assert "uniform" in health["backends"]
    assert client.get("/cluster/peers").json() == []


def test_daemon_mounts_cluster_routes(server_node):
    config = DaemonConfig()
    app = create_daemon_app(config, node=server_node)
    client = TestClient(app)
    assert client.get("/cluster/health").json()["status"] == "ok"


def test_rpc_client_rejects_bad_node_id():
    with pytest.raises(SpecError):
        RPCClient(node_id="")


def test_rpc_client_rejects_bad_timeout():
    with pytest.raises(SpecError):
        RPCClient(node_id="x", timeout=0)
