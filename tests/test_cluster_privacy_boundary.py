"""Tests for slice 211 — privacy boundary enforcement."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.privacy_boundary import (
    SENSITIVE_PREFIX,
    PrivacyBoundary,
)
from hugrgate.cluster.protocol import (
    ClusterMessage,
    MessageType,
    decode_message,
)
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import PrivacyViolation
from hugrgate.serde import policy_to_dict
from hugrgate.server import build_gate


@pytest.fixture
def server_node():
    return ClusterNode(NodeIdentity.generate("srv"), build_gate())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["ignore", "escalate"])


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node
        self.last_payload = None

    def handle_request(self, request):
        message = decode_message(request.content)
        self.last_payload = dict(message.payload)
        reply = self.node.dispatch(message)
        return httpx.Response(200, json={"envelope": reply.to_dict()})


@pytest.fixture
def rpc(server_node):
    transport = _Loopback(server_node)
    client = RPCClient(node_id=NodeIdentity.generate().node_id,
                       http_client=httpx.Client(transport=transport))
    yield client, transport
    client.close()


def _remote(**kw):
    kw.setdefault("remote_inference", True)
    return DecisionPolicy(**kw)


# --- PrivacyBoundary unit ------------------------------------------------------

def test_redact_drops_prefixed_and_extra_fields():
    boundary = PrivacyBoundary()
    state = {"text": "hi", "private_ssn": "123", "age": 3,
             "token": "abc"}
    clean, dropped = boundary.redact_state(state, {"token"})
    assert clean == {"text": "hi", "age": 3}
    assert dropped == ["private_ssn", "token"]
    # input not mutated
    assert "private_ssn" in state


def test_redact_nothing_sensitive():
    clean, dropped = PrivacyBoundary().redact_state({"a": 1})
    assert clean == {"a": 1} and dropped == []


def test_is_sensitive():
    b = PrivacyBoundary()
    assert b.is_sensitive("private_x")
    assert b.is_sensitive("k", {"k"})
    assert not b.is_sensitive("public")


def test_check_outbound_allowed():
    PrivacyBoundary().check_outbound_allowed(_remote())
    with pytest.raises(PrivacyViolation, match="remote_inference"):
        PrivacyBoundary().check_outbound_allowed(DecisionPolicy())
    with pytest.raises(PrivacyViolation, match="local-only"):
        PrivacyBoundary().check_outbound_allowed(
            _remote(privacy_class="strict"))


def test_check_rejects_non_policy():
    with pytest.raises(PrivacyViolation):
        PrivacyBoundary().check_outbound_allowed("nope")


def test_prepare_outbound_combines():
    clean, dropped = PrivacyBoundary().prepare_outbound(
        _remote(), {"a": 1, "private_b": 2})
    assert clean == {"a": 1} and dropped == ["private_b"]
    with pytest.raises(PrivacyViolation):
        PrivacyBoundary().prepare_outbound(DecisionPolicy(), {"a": 1})


def test_custom_prefix():
    b = PrivacyBoundary(sensitive_prefix="secret_")
    clean, dropped = b.redact_state({"secret_a": 1, "private_b": 2})
    assert clean == {"private_b": 2} and dropped == ["secret_a"]
    with pytest.raises(ValueError):
        PrivacyBoundary(sensitive_prefix="")


def test_sensitive_prefix_constant():
    assert SENSITIVE_PREFIX == "private_"


# --- RPC integration ---------------------------------------------------------------

def test_rpc_redacts_sensitive_fields(rpc, server_node, spec):
    client, transport = rpc
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    result = client.decide(
        peer, spec,
        {"text": "escalate", "private_ssn": "123-45"},
        policy=_remote())
    assert result.value in ("ignore", "escalate")
    # the peer never saw the sensitive field...
    assert "private_ssn" not in transport.last_payload["state"]
    assert transport.last_payload["state"]["text"] == "escalate"
    # ...but the redaction is reported, not silent
    assert transport.last_payload["redacted_fields"] == ["private_ssn"]
    assert result.metadata["redacted_fields"] == ["private_ssn"]


def test_rpc_strict_policy_blocked_client_side(rpc, server_node, spec):
    client, _ = rpc
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    with pytest.raises(PrivacyViolation, match="local-only"):
        client.decide(peer, spec, {"text": "x"},
                      policy=_remote(privacy_class="strict"))


def test_server_rejects_strict_policy(server_node, spec):
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="ab" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"text": "x"},
                 "policy": policy_to_dict(
                     _remote(privacy_class="strict"))})
    reply = server_node.dispatch(message)
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "privacy_violation"


def test_batch_redacts_per_item(rpc, server_node, spec):
    client, _transport = rpc
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    results = client.batch(
        peer,
        [{"spec": spec,
          "state": {"text": "a", "private_x": 1}},
         {"spec": spec, "state": {"text": "b"}}],
        policy=_remote())
    assert all("result" in r for r in results)
    assert results[0]["result"]["metadata"]["redacted_fields"] == [
        "private_x"]
    assert "redacted_fields" not in results[1]["result"]["metadata"]


def test_batch_rejects_bad_item_policy(rpc, server_node, spec):
    from hugrgate.errors import SpecError
    client, _ = rpc
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    with pytest.raises(SpecError, match="batch item 'policy'"):
        client.batch(peer, [{"spec": spec, "state": {},
                             "policy": "not-a-policy"}],
                     policy=_remote())


def test_batch_item_dict_policy_checked(rpc, server_node, spec):
    client, _ = rpc
    peer = PeerRecord(node_id=server_node.node_id, host="h", port=1)
    strict_dict = policy_to_dict(_remote(privacy_class="strict"))
    with pytest.raises(PrivacyViolation, match="local-only"):
        client.batch(peer, [{"spec": spec, "state": {},
                             "policy": strict_dict}],
                     policy=_remote())
