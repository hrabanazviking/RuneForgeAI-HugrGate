"""Slice 132 — cost-quality objective tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.cost_quality import (
    CostQualityObjective,
    RouteObjective,
    RoutingCandidate,
)
from hugrgate.errors import SpecError


def cand(name="a", quality=0.8, cost=1.0, **kw):
    params = dict(name=name, quality=quality, cost=cost,
                  latency_ms=100.0, energy_wh=0.01)
    params.update(kw)
    return RoutingCandidate(**params)


# --- success ---------------------------------------------------------------

def test_candidate_contract_validation():
    c = cand()
    assert c.to_dict()["name"] == "a"

def test_cheaper_wins_at_equal_quality():
    obj = CostQualityObjective(quality_weight=1.0, cost_weight=1.0,
                               cost_scale=10.0)
    cheap, pricey = cand("cheap", cost=1.0), cand("pricey", cost=9.0)
    assert obj.score(cheap) > obj.score(pricey)
    assert obj.rank([pricey, cheap])[0].name == "cheap"

def test_quality_can_outweigh_cost():
    obj = CostQualityObjective(quality_weight=10.0, cost_weight=1.0,
                               cost_scale=10.0)
    great = cand("great", quality=1.0, cost=9.0)
    meh = cand("meh", quality=0.5, cost=1.0)
    assert obj.score(great) > obj.score(meh)

def test_pure_cost_minimization():
    obj = CostQualityObjective(quality_weight=0.0, cost_weight=1.0)
    assert obj.rank([cand("a", cost=5.0), cand("b", cost=1.0)])[0].name == "b"

def test_max_affordable_quality_loss_inverts_scalarization():
    obj = CostQualityObjective(quality_weight=2.0, cost_weight=1.0,
                               cost_scale=10.0)
    # 5 extra cost units are worth 5/10 * (1/2) = 0.25 quality.
    assert obj.max_affordable_quality_loss(5.0) == pytest.approx(0.25)
    assert obj.max_affordable_quality_loss(0.0) == 0.0

def test_rank_is_stable_on_ties():
    obj = CostQualityObjective()
    first, second = cand("a"), cand("b")
    assert [c.name for c in obj.rank([first, second])] == ["a", "b"]

def test_to_dict_round_trip_fields():
    d = CostQualityObjective(quality_weight=2.0, cost_weight=3.0,
                             cost_scale=4.0).to_dict()
    assert d == {"name": "cost_quality", "quality_weight": 2.0,
                 "cost_weight": 3.0, "cost_scale": 4.0}

# --- failure ---------------------------------------------------------------

def test_negative_weights_rejected():
    with pytest.raises(SpecError):
        CostQualityObjective(quality_weight=-1.0)
    with pytest.raises(SpecError):
        CostQualityObjective(cost_weight=-0.5)

def test_all_zero_weights_rejected():
    with pytest.raises(SpecError):
        CostQualityObjective(quality_weight=0.0, cost_weight=0.0)

def test_nonpositive_cost_scale_rejected():
    with pytest.raises(SpecError):
        CostQualityObjective(cost_scale=0.0)

def test_candidate_bounds_enforced():
    with pytest.raises(SpecError):
        cand(quality=1.5)
    with pytest.raises(SpecError):
        cand(cost=-1.0)
    with pytest.raises(SpecError):
        cand(latency_ms=-1.0)
    with pytest.raises(SpecError):
        cand(name="")

def test_negative_extra_cost_rejected():
    with pytest.raises(SpecError):
        CostQualityObjective().max_affordable_quality_loss(-1.0)
