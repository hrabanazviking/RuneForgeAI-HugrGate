"""Tests for slice 208 — mutual authentication."""

from __future__ import annotations

import os
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.auth import (
    AUTH_HEADER,
    Authenticator,
    ClusterKey,
    enable_mutual_auth,
)
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    ClusterMessage,
    MessageType,
    encode_message,
)
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import ClusterAuthError, SpecError
from hugrgate.serde import policy_to_dict
from hugrgate.server import build_gate, create_app


@pytest.fixture
def key():
    return ClusterKey.generate()


@pytest.fixture
def server_node():
    return ClusterNode(NodeIdentity.generate("srv"), build_gate())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["ignore", "escalate"])


def _policy():
    return DecisionPolicy(remote_inference=True)


def _decide_msg(sender, seq=1, trace="ee" * 16, spec=None):
    return ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender=sender, seq=seq,
        trace_id=trace,
        payload={"spec": (spec or DecisionSpec(
            type="categorical",
            options=["ignore", "escalate"])).to_dict(),
                 "state": {"text": "escalate"},
                 "policy": policy_to_dict(_policy())})


# --- ClusterKey ---------------------------------------------------------------

def test_key_generate_save_load_round_trip(tmp_path, key):
    path = tmp_path / "cluster.key"
    key.save(path)
    assert ClusterKey.load(path).key == key.key
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_key_rejects_bad_length():
    with pytest.raises(SpecError):
        ClusterKey(key=b"short")


def test_key_load_missing(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        ClusterKey.load(tmp_path / "nope.key")


def test_key_load_malformed(tmp_path):
    path = tmp_path / "bad.key"
    path.write_text('{"key": "zz"}', encoding="utf-8")
    with pytest.raises(SpecError, match="malformed"):
        ClusterKey.load(path)


# --- Authenticator --------------------------------------------------------------

def test_seal_verify_round_trip(key):
    auth = Authenticator(key)
    tag = auth.seal(b"hello")
    assert auth.verify(b"hello", tag)
    assert len(tag) == 64


def test_verify_rejects_tampered_data(key):
    auth = Authenticator(key)
    tag = auth.seal(b"hello")
    assert not auth.verify(b"hellO", tag)


def test_verify_rejects_wrong_key():
    auth = Authenticator(ClusterKey.generate())
    other = Authenticator(ClusterKey.generate())
    assert not other.verify(b"data", auth.seal(b"data"))


def test_verify_never_raises_on_garbage(key):
    auth = Authenticator(key)
    assert not auth.verify(b"data", None)
    assert not auth.verify(b"data", "not-hex!!")
    assert not auth.verify(b"data", "ab" * 10)  # wrong length


def test_authenticator_rejects_non_key():
    with pytest.raises(SpecError):
        Authenticator(key="nope")  # type: ignore[arg-type]


def test_seal_rejects_non_bytes(key):
    with pytest.raises(SpecError):
        Authenticator(key).seal("text")  # type: ignore[arg-type]


# --- node-level verification ------------------------------------------------------

def test_valid_tag_dispatches(server_node, key, spec):
    provider = enable_mutual_auth(server_node, key)
    sender = NodeIdentity.generate().node_id
    message = _decide_msg(sender, spec=spec)
    raw = encode_message(message)
    reply = server_node.dispatch(message, auth_tag=provider(raw),
                                 raw=raw)
    assert reply.msg_type is MessageType.DECIDE_RESPONSE


def test_missing_tag_rejected(server_node, key):
    enable_mutual_auth(server_node, key)
    message = _decide_msg(NodeIdentity.generate().node_id)
    reply = server_node.dispatch(message, raw=encode_message(message))
    assert reply.payload["error"]["code"] == "cluster_auth_error"


def test_bad_tag_rejected(server_node, key):
    enable_mutual_auth(server_node, key)
    sender = NodeIdentity.generate().node_id
    message = _decide_msg(sender)
    raw = encode_message(message)
    tampered = bytearray(raw)
    tampered[-10] ^= 0xFF  # flip a payload byte; tag now stale
    reply = server_node.dispatch(
        message, auth_tag=Authenticator(key).seal(raw),
        raw=bytes(tampered))
    assert reply.payload["error"]["code"] == "cluster_auth_error"


def test_wrong_key_rejected(server_node, key):
    enable_mutual_auth(server_node, key)
    sender = NodeIdentity.generate().node_id
    message = _decide_msg(sender)
    raw = encode_message(message)
    tag = Authenticator(ClusterKey.generate()).seal(raw)
    reply = server_node.dispatch(message, auth_tag=tag, raw=raw)
    assert reply.payload["error"]["code"] == "cluster_auth_error"


def test_replay_rejected(server_node, key):
    provider = enable_mutual_auth(server_node, key)
    sender = NodeIdentity.generate().node_id
    message = _decide_msg(sender, seq=5)
    raw = encode_message(message)
    first = server_node.dispatch(message, auth_tag=provider(raw),
                                 raw=raw)
    assert first.msg_type is MessageType.DECIDE_RESPONSE
    replay = server_node.dispatch(message, auth_tag=provider(raw),
                                  raw=raw)
    assert replay.payload["error"]["code"] == "cluster_auth_error"
    assert "replay" in replay.payload["error"]["message"]
    # a higher seq from the same sender still works
    newer = _decide_msg(sender, seq=6)
    raw_new = encode_message(newer)
    assert server_node.dispatch(
        newer, auth_tag=provider(raw_new),
        raw=raw_new).msg_type is MessageType.DECIDE_RESPONSE


def test_auth_off_by_default(server_node):
    message = _decide_msg(NodeIdentity.generate().node_id)
    reply = server_node.dispatch(message)  # no tag, no raw
    assert reply.msg_type is MessageType.DECIDE_RESPONSE


def test_require_auth_without_authenticator_is_an_error(server_node):
    server_node.require_auth = True  # misconfigured: no authenticator
    message = _decide_msg(NodeIdentity.generate().node_id)
    reply = server_node.dispatch(message, auth_tag="ab" * 32,
                                 raw=b"x")
    assert reply.payload["error"]["code"] == "cluster_auth_error"


# --- wire: header round trip ------------------------------------------------------

class _HeaderCapturingTransport(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node
        self.last_headers = None

    def handle_request(self, request):
        from hugrgate.cluster.protocol import decode_message
        self.last_headers = dict(request.headers)
        message = decode_message(request.content)
        reply = self.node.dispatch(
            message,
            auth_tag=request.headers.get(AUTH_HEADER),
            raw=request.content)
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def test_rpc_client_sends_mac_header(server_node, key, spec):
    provider = enable_mutual_auth(server_node, key)
    transport = _HeaderCapturingTransport(server_node)
    rpc = RPCClient(node_id=NodeIdentity.generate().node_id,
                    mac_provider=provider,
                    http_client=httpx.Client(transport=transport))
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    try:
        result = rpc.decide(peer, spec, {"text": "escalate"},
                            policy=_policy())
        assert result.value in ("ignore", "escalate")
        assert transport.last_headers["x-cluster-mac"]
    finally:
        rpc.close()


def test_rpc_without_mac_fails_against_authed_node(server_node, key,
                                                   spec):
    enable_mutual_auth(server_node, key)  # server only
    transport = _HeaderCapturingTransport(server_node)
    rpc = RPCClient(node_id=NodeIdentity.generate().node_id,
                    http_client=httpx.Client(transport=transport))
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    try:
        with pytest.raises(ClusterAuthError):
            rpc.decide(peer, spec, {"text": "escalate"},
                       policy=_policy())
    finally:
        rpc.close()


def test_http_route_passes_mac_header(server_node, key, spec):
    provider = enable_mutual_auth(server_node, key)
    client = TestClient(create_app(node=server_node))
    message = _decide_msg(NodeIdentity.generate().node_id, spec=spec)
    raw = encode_message(message)
    r = client.post(CLUSTER_RPC_PATH, content=raw,
                    headers={AUTH_HEADER: provider(raw)})
    reply = ClusterMessage.from_dict(r.json()["envelope"])
    assert reply.msg_type is MessageType.DECIDE_RESPONSE
    # and without the header it fails closed (still HTTP 200 envelope)
    r2 = client.post(CLUSTER_RPC_PATH, content=raw)
    reply2 = ClusterMessage.from_dict(r2.json()["envelope"])
    assert reply2.payload["error"]["code"] == "cluster_auth_error"


# --- taxonomy ---------------------------------------------------------------------

def test_cluster_auth_error_taxonomy():
    err = ClusterAuthError("bad tag")
    assert err.code == "cluster_auth_error"
    assert err.recoverable is False
    assert "cluster_auth_error" in str(err)
    rebuilt = ClusterAuthError.from_dict(err.to_dict())
    assert type(rebuilt) is ClusterAuthError
