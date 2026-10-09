"""Tests for slice 210 — policy propagation."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.policy_sync import (
    PolicyPropagator,
    PolicyVersion,
    merge_policies,
)
from hugrgate.cluster.protocol import (
    ClusterMessage,
    MessageType,
    decode_message,
)
from hugrgate.errors import PolicyError, SpecError
from hugrgate.serde import policy_to_dict
from hugrgate.server import build_gate


def _p(**kw):
    return DecisionPolicy(**kw)


# --- merge semantics -----------------------------------------------------------

def test_strictest_wins_safety_fields():
    lax = _p(minimum_probability=0.1, remote_inference=True,
             privacy_class="standard", maximum_latency_ms=1000.0,
             max_cost=5.0, fallback_behavior="safe_default",
             allowed_backends=["a", "b"])
    strict = _p(minimum_probability=0.9, remote_inference=False,
                privacy_class="strict", maximum_latency_ms=100.0,
                max_cost=1.0, fallback_behavior="abstain",
                allowed_backends=["b", "c"])
    merged = merge_policies(lax, strict)
    assert merged.minimum_probability == 0.9
    assert merged.remote_inference is False  # one veto disables
    assert merged.privacy_class == "strict"
    assert merged.maximum_latency_ms == 100.0
    assert merged.max_cost == 1.0
    assert merged.fallback_behavior == "abstain"
    assert merged.allowed_backends == ["b"]  # intersection


def test_merge_is_symmetric_for_safety_fields():
    a = _p(minimum_probability=0.8, privacy_class="strict")
    b = _p(minimum_probability=0.2, privacy_class="standard")
    ab, ba = merge_policies(a, b), merge_policies(b, a)
    assert policy_to_dict(ab) == policy_to_dict(ba)


def test_fallback_conservative_ordering():
    assert merge_policies(
        _p(fallback_behavior="safe_default"),
        _p(fallback_behavior="escalate")).fallback_behavior == "escalate"
    assert merge_policies(
        _p(fallback_behavior="escalate"),
        _p(fallback_behavior="abstain")).fallback_behavior == "abstain"


def test_review_band_envelope_union():
    merged = merge_policies(_p(review_band=(0.4, 0.6)),
                            _p(review_band=(0.5, 0.8)))
    assert merged.review_band == (0.4, 0.8)
    assert merge_policies(_p(), _p(review_band=(0.1, 0.2))
                          ).review_band == (0.1, 0.2)


def test_none_bounds_stay_none():
    merged = merge_policies(_p(), _p(maximum_latency_ms=50.0))
    assert merged.maximum_latency_ms == 50.0
    assert merge_policies(_p(), _p()).max_cost is None


def test_allowed_backends_none_means_unrestricted():
    merged = merge_policies(_p(), _p(allowed_backends=["x"]))
    assert merged.allowed_backends == ["x"]
    assert merge_policies(_p(), _p()).allowed_backends is None


# --- PolicyVersion -----------------------------------------------------------------

def test_version_ordering_and_bump():
    v1 = PolicyVersion(1, timestamp=100.0, node_id="a")
    v2 = v1.bump("a")
    assert v2 > v1 and v2.version == 2 and v2.node_id == "a"
    assert PolicyVersion.from_dict(v1.to_dict()) == v1


def test_version_rejects_bad_input():
    with pytest.raises(SpecError):
        PolicyVersion(-1)
    with pytest.raises(SpecError):
        PolicyVersion.from_dict({"nope": True})
    with pytest.raises(SpecError):
        PolicyVersion.from_dict("x")


# --- PolicyPropagator ------------------------------------------------------------------

def test_update_bumps_version():
    prop = PolicyPropagator(node_id="n1")
    v0 = prop.version
    v1 = prop.update(_p(minimum_probability=0.5))
    assert v1 > v0
    assert prop.policy.minimum_probability == 0.5


def test_update_rejects_non_policy():
    with pytest.raises(PolicyError):
        PolicyPropagator().update({"minimum_probability": 0.5})


def test_receive_merges_and_reports_changed():
    a = PolicyPropagator(node_id="a")
    b = PolicyPropagator(node_id="b")
    b.update(_p(minimum_probability=0.7, privacy_class="strict"))
    snap = b.snapshot()
    changed = a.receive(snap["policy"], snap["version"])
    assert changed is True
    assert a.policy.minimum_probability == 0.7
    assert a.policy.privacy_class == "strict"
    # receiving the same again: merged policy identical -> not changed
    assert a.receive(snap["policy"], snap["version"]) is False


def test_preferred_backends_newest_wins():
    a = PolicyPropagator(node_id="a")
    b = PolicyPropagator(node_id="b")
    a.update(_p(preferred_backends=["old"]))
    old_version = a.version
    b.update(_p(preferred_backends=["new"]))
    a.receive(b.snapshot()["policy"], b.snapshot()["version"])
    assert a.policy.preferred_backends == ["new"]
    # stale re-send of the old version must not clobber
    stale = PolicyPropagator(node_id="b")
    stale._version = old_version  # simulate an old stamp
    stale._policy = _p(preferred_backends=["stale"])
    a.receive(stale.snapshot()["policy"], stale.snapshot()["version"])
    assert a.policy.preferred_backends == ["new"]


def test_receive_rejects_bad_version():
    prop = PolicyPropagator()
    with pytest.raises(SpecError):
        prop.receive(policy_to_dict(_p()), {"version": "x"})


def test_snapshot_wire_shape():
    snap = PolicyPropagator(node_id="n").snapshot()
    assert set(snap) == {"policy", "version"}
    assert snap["version"]["node_id"] == "n"


# --- node integration ---------------------------------------------------------------------

def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _push(node, policy, version):
    return node.dispatch(ClusterMessage(
        msg_type=MessageType.POLICY_PUSH, sender="ab" * 32, seq=1,
        payload={"policy": policy_to_dict(policy),
                 "version": version.to_dict()}))


def test_node_handles_policy_push_and_pull():
    node = _node()
    other = PolicyPropagator(node_id="peer")
    other.update(_p(minimum_probability=0.6,
                    remote_inference=False))
    reply = _push(node, other.policy, other.version)
    assert reply.msg_type is MessageType.POLICY_RESPONSE
    assert reply.payload["changed"] is True
    # strictest-wins: remote veto disabled remote inference cluster-wide
    assert node.policy_sync.policy.remote_inference is False
    assert node.policy_sync.policy.minimum_probability == 0.6

    pull = node.dispatch(ClusterMessage(
        msg_type=MessageType.POLICY_PULL, sender="ab" * 32, seq=2,
        payload={}))
    assert pull.msg_type is MessageType.POLICY_RESPONSE
    assert pull.payload["policy"]["minimum_probability"] == 0.6


def test_node_rejects_malformed_policy_push():
    node = _node()
    reply = node.dispatch(ClusterMessage(
        msg_type=MessageType.POLICY_PUSH, sender="ab" * 32, seq=1,
        payload={"policy": {"bogus_key": 1}, "version": {"version": 1}}))
    assert reply.msg_type is MessageType.ERROR
    assert reply.payload["error"]["code"] == "policy_error"


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        message = decode_message(request.content)
        reply = self.node.dispatch(message)
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def test_propagate_policy_to_peers():
    from hugrgate.cluster.rpc import RPCClient

    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer_b = PeerRecord(node_id=node_b.node_id, host="h", port=1)
    node_a.discovery.add_adapter(_StaticPeers([peer_b]))

    node_a.policy_sync.update(_p(minimum_probability=0.75))
    outcomes = node_a.propagate_policy()
    assert outcomes == {node_b.node_id: "ok"}
    assert node_b.policy_sync.policy.minimum_probability == 0.75


def test_propagate_policy_survives_dead_peer():
    from hugrgate.cluster.rpc import RPCClient

    node_a, node_b = _node("a"), _node("b")
    dead = PeerRecord(node_id="cc" * 32, host="127.0.0.1", port=59997)
    live = PeerRecord(node_id=node_b.node_id, host="h", port=1)
    node_a.discovery.add_adapter(_StaticPeers([dead, live]))
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_DeadThenLoopback(node_b)))
    outcomes = node_a.propagate_policy()
    assert outcomes[live.node_id] == "ok"
    assert "unreachable" in outcomes[dead.node_id] or \
        "backend_unavailable" in outcomes[dead.node_id]


class _StaticPeers(Discovery):
    def __init__(self, peers):
        self._peers = peers
        self.name = "test-static"

    def peers(self):
        return list(self._peers)


class _DeadThenLoopback(httpx.BaseTransport):
    """Fails for the dead peer, dispatches for the live one."""

    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        if "59997" in str(request.url):
            raise httpx.ConnectError("nope")
        message = decode_message(request.content)
        reply = self.node.dispatch(message)
        return httpx.Response(200, json={"envelope": reply.to_dict()})
