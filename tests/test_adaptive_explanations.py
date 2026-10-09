"""Slice 147 - adaptive-route explanations tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.competence import BackendCompetenceProfiles
from hugrgate.adaptive.cost_quality import CostQualityObjective, RoutingCandidate
from hugrgate.adaptive.explanations import (
    AdaptiveRouteExplainer,
    RouteExplanation,
)
from hugrgate.errors import SpecError


def cand(name, quality=0.8, cost=1.0):
    return RoutingCandidate(name=name, quality=quality, cost=cost,
                            latency_ms=100.0, energy_wh=0.01)


# --- success ---------------------------------------------------------------

def test_explain_names_winner_runner_up_and_margin():
    explainer = AdaptiveRouteExplainer()
    exp = explainer.explain("b", {"a": 0.5, "b": 0.9, "c": 0.7})
    assert isinstance(exp, RouteExplanation)
    assert exp.chosen == "b"
    assert exp.runner_up == "c"
    assert exp.margin == pytest.approx(0.2)
    assert "b" in exp.text and "0.9000" in exp.text

def test_single_candidate_explains_itself():
    explainer = AdaptiveRouteExplainer()
    exp = explainer.explain("only", {"only": 0.3})
    assert exp.runner_up is None and exp.margin == 0.0
    assert "only candidate" in exp.text

def test_feature_contributions_ranked_by_impact():
    explainer = AdaptiveRouteExplainer(top_k_features=2)
    exp = explainer.explain(
        "b", {"a": 0.5, "b": 0.9},
        features={"x0": 1.0, "x1": 0.2, "bias": 1.0},
        feature_weights={"x0": 2.0, "x1": -5.0, "bias": 0.1})
    assert len(exp.top_features) == 2
    # |-5.0x0.2|=1.0 < |2.0x1.0|=2.0 → x0 first.
    assert exp.top_features[0].feature == "x0"
    assert exp.top_features[0].contribution == pytest.approx(2.0)
    assert "x0" in exp.text

def test_competence_note_cites_track_record():
    reg = BackendCompetenceProfiles()
    for _ in range(10):
        reg.observe("b", quality=0.9)
    explainer = AdaptiveRouteExplainer(profiles=reg)
    exp = explainer.explain("b", {"a": 0.5, "b": 0.9})
    assert exp.competence_note is not None
    assert "10 recorded attempts" in exp.competence_note
    assert "Wilson lower" in exp.competence_note
    assert exp.competence_note in exp.text

def test_competence_note_honest_about_no_history():
    explainer = AdaptiveRouteExplainer(
        profiles=BackendCompetenceProfiles())
    exp = explainer.explain("fresh", {"fresh": 0.6})
    assert "No competence history" in exp.competence_note

def test_objective_note_included():
    explainer = AdaptiveRouteExplainer()
    exp = explainer.explain("b", {"a": 0.5, "b": 0.9},
                            objective_note="weights: quality=1, cost=2")
    assert exp.objective_note == "weights: quality=1, cost=2"
    assert "weights: quality=1, cost=2" in exp.text

def test_explain_candidates_convenience():
    explainer = AdaptiveRouteExplainer()
    obj = CostQualityObjective(cost_scale=10.0)
    exp = explainer.explain_candidates(
        [cand("cheap", quality=0.8, cost=1.0),
         cand("pricey", quality=0.8, cost=9.0)], obj.score)
    assert exp.chosen == "cheap"
    assert exp.runner_up == "pricey"

def test_to_dict_round_trip_shape():
    explainer = AdaptiveRouteExplainer()
    exp = explainer.explain("b", {"a": 0.5, "b": 0.9},
                            features={"x0": 1.0},
                            feature_weights={"x0": 2.0})
    d = exp.to_dict()
    assert d["chosen"] == "b" and d["margin"] == pytest.approx(0.4)
    assert d["top_features"][0]["feature"] == "x0"

# --- failure ---------------------------------------------------------------

def test_chosen_without_score_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteExplainer().explain("ghost", {"a": 0.5})

def test_explain_candidates_empty_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteExplainer().explain_candidates([], lambda c: 0.0)

def test_bad_top_k_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteExplainer(top_k_features=0)
