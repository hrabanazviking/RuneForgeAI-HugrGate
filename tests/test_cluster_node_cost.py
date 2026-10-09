"""Tests for slice 215 — node cost scoring."""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.node_cost import CostModel
from hugrgate.errors import SpecError
from hugrgate.server import build_gate


class _Static(Discovery):
    name = "test"

    def __init__(self, peers):
        self._peers = peers

    def peers(self):
        return list(self._peers)


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- model unit ------------------------------------------------------------------

def test_unknown_peer_is_free():
    model = CostModel()
    assert model.cost_of("new") == 0.0
    assert model.score("new") == 1.0
    assert model.affordable("new", 0.0)


def test_score_diminishes_with_cost():
    model = CostModel()
    model.set_cost("a", 1.0)
    model.set_cost("b", 9.0)
    assert model.score("a") == pytest.approx(0.5)
    assert model.score("b") == pytest.approx(0.1)
    assert model.score("a") > model.score("b")


def test_set_cost_rejects_bad_values():
    model = CostModel()
    for bad in (-1.0, float("inf"), float("nan"), "x"):
        with pytest.raises(SpecError):
            model.set_cost("p", bad)


def test_affordable_budget_gate():
    model = CostModel()
    model.set_cost("cheap", 2.0)
    model.set_cost("pricey", 8.0)
    assert model.affordable("cheap", 5.0)
    assert not model.affordable("pricey", 5.0)
    assert model.affordable("pricey", None)  # no budget: everyone fits


def test_reset_forgets_cost():
    model = CostModel()
    model.set_cost("p", 10.0)
    assert model.score("p") < 1.0
    model.reset("p")
    assert model.score("p") == 1.0


# --- router integration ---------------------------------------------------------------

def _peer(node, port):
    return PeerRecord(node_id=node.node_id, host="h", port=port,
                      capabilities=node.capabilities())


def test_budget_veto_excludes_pricey_peer(spec):
    node_a = _node("a")
    cheap, pricey = _node("cheap"), _node("pricey")
    node_a.discovery.add_adapter(
        _Static([_peer(cheap, 1), _peer(pricey, 2)]))
    node_a.costs.set_cost(cheap.node_id, 2.0)
    node_a.costs.set_cost(pricey.node_id, 8.0)
    policy = DecisionPolicy(remote_inference=True, max_cost=5.0)
    ids = [c.node_id for c in node_a.router.route(spec, policy)]
    assert cheap.node_id in ids
    assert pricey.node_id not in ids


def test_no_budget_everyone_routes(spec):
    node_a = _node("a")
    pricey = _node("pricey")
    node_a.discovery.add_adapter(_Static([_peer(pricey, 2)]))
    node_a.costs.set_cost(pricey.node_id, 100.0)
    ids = [c.node_id for c in node_a.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert pricey.node_id in ids


def test_unknown_cost_never_excluded(spec):
    node_a = _node("a")
    peer_node = _node("peer")
    node_a.discovery.add_adapter(_Static([_peer(peer_node, 1)]))
    # No cost set: treated as free, fits any budget.
    policy = DecisionPolicy(remote_inference=True, max_cost=0.0)
    ids = [c.node_id for c in node_a.router.route(spec, policy)]
    assert peer_node.node_id in ids


def test_refresh_scores_carries_cost(spec):
    node_a = _node("a")
    free, costly = _node("free"), _node("costly")
    node_a.discovery.add_adapter(
        _Static([_peer(free, 1), _peer(costly, 2)]))
    node_a.costs.set_cost(costly.node_id, 3.0)
    node_a.refresh_scores()
    assert node_a.router.scores_for(free.node_id).cost == 1.0
    assert node_a.router.scores_for(costly.node_id).cost == \
        pytest.approx(0.25)
    ordered = [c.node_id for c in node_a.router.route(
        spec, DecisionPolicy(remote_inference=True))]
    assert ordered[1] == free.node_id
    assert ordered[2] == costly.node_id
