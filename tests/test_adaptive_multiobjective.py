"""Slice 136 — multi-objective routing tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.cost_quality import (
    CostQualityObjective,
    RoutingCandidate,
)
from hugrgate.adaptive.energy_quality import EnergyQualityObjective
from hugrgate.adaptive.latency_quality import LatencyQualityObjective
from hugrgate.adaptive.multiobjective import (
    MODES,
    MultiObjectiveRouter,
    dominates,
    pareto_frontier,
)
from hugrgate.errors import SpecError


def cand(name, quality, cost, latency_ms, energy_wh=0.01):
    return RoutingCandidate(name=name, quality=quality, cost=cost,
                            latency_ms=latency_ms, energy_wh=energy_wh)


CANDS = [
    cand("fast_cheap", 0.70, 0.10, 50.0),
    cand("best_quality", 0.95, 5.00, 900.0),
    cand("balanced", 0.85, 1.00, 200.0),
]


# --- success ---------------------------------------------------------------

def test_weighted_sum_combines_objectives():
    router = MultiObjectiveRouter([
        (CostQualityObjective(cost_scale=10.0), 1.0),
        (LatencyQualityObjective(latency_scale=1000.0), 1.0),
    ])
    ranked = router.rank(CANDS)
    # balanced: (0.85-0.10) + (0.85-0.20) = 1.40 — best blend of the two.
    assert next(c.name for c in ranked) == "balanced"
    # Weighted sum is linear in the weights: doubling one weight doubles
    # its influence.
    s1 = router.score(CANDS[0])
    router2 = MultiObjectiveRouter([
        (CostQualityObjective(cost_scale=10.0), 2.0),
        (LatencyQualityObjective(latency_scale=1000.0), 1.0),
    ])
    assert router2.score(CANDS[0]) != s1

def test_lexicographic_mode_quality_first():
    router = MultiObjectiveRouter([
        (CostQualityObjective(quality_weight=1.0, cost_weight=0.0), 1.0),
        (LatencyQualityObjective(quality_weight=0.0, latency_weight=1.0,
                                 latency_scale=1000.0), 1.0),
    ], mode="lexicographic")
    assert router.best(CANDS).name == "best_quality"

def test_lexicographic_falls_through_on_ties():
    router = MultiObjectiveRouter([
        (CostQualityObjective(quality_weight=1.0, cost_weight=0.0), 1.0),
        (CostQualityObjective(quality_weight=0.0, cost_weight=1.0,
                              cost_scale=10.0), 1.0),
    ], mode="lexicographic")
    tied = [cand("x", 0.8, 5.0, 100.0), cand("y", 0.8, 1.0, 100.0)]
    assert router.best(tied).name == "y"  # quality tied -> cheaper wins

def test_pareto_frontier_keeps_nondominated():
    dominated = cand("dominated", 0.50, 9.0, 1500.0)
    frontier = pareto_frontier([*CANDS, dominated])
    names = [c.name for c in frontier]
    assert "dominated" not in names
    assert set(names) == {"fast_cheap", "best_quality", "balanced"}
    assert names == ["fast_cheap", "best_quality", "balanced"]  # input order

def test_dominates_semantics():
    a = cand("a", 0.9, 1.0, 100.0)
    b = cand("b", 0.8, 2.0, 200.0)
    assert dominates(a, b) and not dominates(b, a)
    assert not dominates(a, a)  # not strictly better than itself

def test_explain_weights_is_auditable():
    router = MultiObjectiveRouter([
        (CostQualityObjective(), 2.0),
        (EnergyQualityObjective(), 1.0),
    ])
    weights = router.explain_weights()
    assert weights[0] == {"objective": "cost_quality", "weight": 2.0,
                          "mode": "weighted_sum", "priority": 0}
    assert weights[1]["objective"] == "energy_quality"

def test_modes_constant():
    assert set(MODES) == {"weighted_sum", "lexicographic"}

# --- failure ---------------------------------------------------------------

def test_unknown_mode_rejected():
    with pytest.raises(SpecError):
        MultiObjectiveRouter([(CostQualityObjective(), 1.0)], mode="magic")

def test_empty_objectives_rejected():
    with pytest.raises(SpecError):
        MultiObjectiveRouter([])

def test_negative_weight_rejected():
    with pytest.raises(SpecError):
        MultiObjectiveRouter([(CostQualityObjective(), -1.0)])

def test_all_zero_weights_rejected_in_weighted_sum():
    with pytest.raises(SpecError):
        MultiObjectiveRouter([(CostQualityObjective(), 0.0)])

def test_non_objective_rejected():
    with pytest.raises(SpecError):
        MultiObjectiveRouter([("nope", 1.0)])

def test_rank_empty_rejected():
    router = MultiObjectiveRouter([(CostQualityObjective(), 1.0)])
    with pytest.raises(SpecError):
        router.rank([])

def test_lexicographic_has_no_scalar_score():
    router = MultiObjectiveRouter([(CostQualityObjective(), 1.0)],
                                  mode="lexicographic")
    with pytest.raises(SpecError):
        router.score(CANDS[0])
