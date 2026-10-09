"""Tests for slice 212 — distributed ladder routing."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import decode_message
from hugrgate.cluster.routing import (
    DistributedRouter,
    PeerScores,
    RouteCandidate,
)
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    SpecError,
)
from hugrgate.result import DecisionResult
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


class _Boom(Backend):
    name = "boom"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        raise BackendError("boom")


class _Bin(Backend):
    name = "bin"

    def capabilities(self):
        return {"spec_types": ["binary"]}

    def supports(self, spec):
        return spec.type == "binary"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value=True, probability=1.0,
                              distribution={"true": 1.0}, uncertainty=0.0,
                              backend=self.name, model="bin-1")


def _node(name="n", gate=None):
    return ClusterNode(NodeIdentity.generate(name),
                       gate or build_gate())


def _peer_for(node, host="h", port=1):
    return PeerRecord(node_id=node.node_id, host=host, port=port,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _remote():
    return DecisionPolicy(remote_inference=True)


# --- PeerScores ------------------------------------------------------------------

def test_scores_default_perfect():
    s = PeerScores()
    assert (s.health, s.latency, s.cost) == (1.0, 1.0, 1.0)


def test_scores_reject_out_of_range():
    with pytest.raises(SpecError):
        PeerScores(health=1.5)
    with pytest.raises(SpecError):
        PeerScores(cost=-0.1)


def test_router_rejects_bad_weights():
    node = _node()
    with pytest.raises(SpecError):
        DistributedRouter(node, weights={"health": 1.0})
    with pytest.raises(SpecError):
        DistributedRouter(node, weights={"health": -1.0,
                                         "latency": 0.0, "cost": 0.0})
    with pytest.raises(SpecError):
        DistributedRouter(node, weights={"health": 0.0,
                                         "latency": 0.0, "cost": 0.0})
    assert DistributedRouter(node).weights == {"health": 0.5,
                                               "latency": 0.3,
                                               "cost": 0.2}


def test_set_scores_rejects_wrong_type():
    with pytest.raises(SpecError):
        _node().router.set_scores("x", {"health": 1.0})


# --- route() filtering & ordering -----------------------------------------------------

def test_route_local_only_without_peers(spec):
    node = _node()
    candidates = node.router.route(spec, _remote())
    assert [c.kind for c in candidates] == ["local"]


def test_route_local_wins_ties(spec):
    node, peer_node = _node("a"), _node("b")
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    node.router.set_scores(peer_node.node_id, PeerScores(1.0, 1.0, 1.0))
    kinds = [c.kind for c in node.router.route(spec, _remote())]
    assert kinds == ["local", "remote"]


def test_route_orders_peers_by_score(spec):
    node = _node("a")
    good, bad = _node("good"), _node("bad")
    node.discovery.add_adapter(
        _Static([_peer_for(bad), _peer_for(good)]))
    node.router.set_scores(bad.node_id, PeerScores(0.2, 0.2, 0.2))
    node.router.set_scores(good.node_id, PeerScores(0.9, 0.9, 0.9))
    ids = [c.node_id for c in node.router.route(spec, _remote())]
    assert ids == ["local", good.node_id, bad.node_id]


def test_route_weights_change_ordering(spec):
    node = _node("a")
    cheap_slow, pricey_fast = _node("cs"), _node("pf")
    node.discovery.add_adapter(
        _Static([_peer_for(cheap_slow), _peer_for(pricey_fast)]))
    node.router.set_scores(cheap_slow.node_id,
                           PeerScores(health=1.0, latency=0.1, cost=1.0))
    node.router.set_scores(pricey_fast.node_id,
                           PeerScores(health=1.0, latency=1.0, cost=0.1))
    latency_router = DistributedRouter(
        node, weights={"health": 0.0, "latency": 1.0, "cost": 0.0})
    cost_router = DistributedRouter(
        node, weights={"health": 0.0, "latency": 0.0, "cost": 1.0})
    for router in (latency_router, cost_router):
        router.set_scores(cheap_slow.node_id,
                          PeerScores(health=1.0, latency=0.1, cost=1.0))
        router.set_scores(pricey_fast.node_id,
                          PeerScores(health=1.0, latency=1.0, cost=0.1))
    latency_ids = [c.node_id for c in latency_router.route(spec, _remote())]
    cost_ids = [c.node_id for c in cost_router.route(spec, _remote())]
    assert latency_ids[1] == pricey_fast.node_id
    assert cost_ids[1] == cheap_slow.node_id


def test_route_privacy_filters_remote(spec):
    node, peer_node = _node("a"), _node("b")
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    kinds = [c.kind for c in node.router.route(
        spec, DecisionPolicy())]  # remote_inference=False
    assert kinds == ["local"]
    strict = DecisionPolicy(remote_inference=True, privacy_class="strict")
    assert [c.kind for c in node.router.route(spec, strict)] == ["local"]


def test_route_capability_filters_remote(spec):
    node = _node("a")
    gate = HugrGate()
    gate.register(_Bin())
    peer_node = ClusterNode(NodeIdentity.generate("bin-only"), gate)
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    kinds = [c.kind for c in node.router.route(spec, _remote())]
    assert kinds == ["local"]  # peer only speaks binary


def test_route_no_local_backend_still_routes_remote(spec):
    gate = HugrGate()  # empty: nothing local supports the spec
    node = _node("a", gate=gate)
    peer_node = _node("b")
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    candidates = node.router.route(spec, _remote())
    assert [c.kind for c in candidates] == ["remote"]


def test_best_none_when_nothing(spec):
    gate = HugrGate()
    node = _node("a", gate=gate)
    assert node.router.best(spec, _remote()) is None


def test_audit_shape(spec):
    node = _node()
    audit = node.router.audit(spec, _remote())
    assert audit[0]["kind"] == "local"
    assert set(audit[0]) == {"kind", "node_id", "total", "scores",
                            "reasons"}


def test_candidate_node_id():
    assert RouteCandidate(kind="local", peer=None).node_id == "local"


# --- decide() walk -----------------------------------------------------------------------

def _wire_remote(caller, peer_node):
    caller.rpc = RPCClient(
        node_id=caller.node_id,
        http_client=httpx.Client(transport=_Loopback(peer_node)))


def test_decide_local_success(spec):
    node = _node()
    result = node.router.decide(spec, {"text": "a"},
                                policy=_remote())
    assert result.value in ("a", "b")
    assert result.metadata["route"]["kind"] == "local"


def test_decide_falls_back_to_remote(spec):
    gate = HugrGate()
    gate.register(_Boom())  # local always fails
    node = _node("a", gate=gate)
    peer_node = _node("b")
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    _wire_remote(node, peer_node)
    result = node.router.decide(spec, {"text": "a"}, policy=_remote())
    assert result.value in ("a", "b")
    assert result.metadata["route"]["kind"] == "remote"
    assert result.metadata["route"]["node_id"] == peer_node.node_id


def test_decide_all_fail(spec):
    gate = HugrGate()
    gate.register(_Boom())
    node = _node("a", gate=gate)
    dead = PeerRecord(node_id="cc" * 32, host="127.0.0.1", port=59997)
    node.discovery.add_adapter(_Static([dead]))
    with pytest.raises(BackendUnavailable, match="all 2 route"):
        node.router.decide(spec, {"text": "a"}, policy=_remote())


def test_decide_no_route(spec):
    gate = HugrGate()
    node = _node("a", gate=gate)
    with pytest.raises(BackendUnavailable, match="no route"):
        node.router.decide(spec, {"text": "a"}, policy=_remote())


def test_decide_abstention_propagates(spec):
    node = _node()
    policy = DecisionPolicy(remote_inference=True,
                            minimum_probability=0.99)
    peer_node = _node("b")
    node.discovery.add_adapter(_Static([_peer_for(peer_node)]))
    _wire_remote(node, peer_node)
    with pytest.raises(Abstention):
        node.router.decide(spec, {"text": "zzz no match"},
                            policy=policy)
