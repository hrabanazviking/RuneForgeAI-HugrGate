"""Slice 106 — Bayesian model averaging adapter.

Posterior model probabilities from priors + accumulated predictive
log-likelihoods; the "bma" combiner averages member distributions
with the posterior weights.
"""

from __future__ import annotations

import math

import pytest
from ensemble_fakes import ConstantBackend

from hugrgate import DecisionSpec
from hugrgate.ensemble import (
    BayesianModelAverager,
    Ensemble,
    bma_combine,
    predictive_log_likelihood,
)
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError, PolicyError

TWO = DecisionSpec(type="categorical", options=["alpha", "beta"])


def _ctx(spec=None, fitted=None):
    return StrategyContext(spec=spec or TWO, fitted=fitted)


def _votes():
    return [
        MemberVote(backend="a", value="alpha", probability=0.8,
                   distribution={"alpha": 0.8, "beta": 0.2}, weight=1.0),
        MemberVote(backend="b", value="beta", probability=0.7,
                   distribution={"alpha": 0.3, "beta": 0.7}, weight=1.0),
    ]


# --- success -----------------------------------------------------------------

def test_no_observations_falls_back_to_prior():
    avg = BayesianModelAverager(["a", "b"])
    assert avg.posterior_weights() == pytest.approx({"a": 0.5, "b": 0.5})
    assert avg.observation_counts == {"a": 0, "b": 0}


def test_exact_posterior_math():
    avg = BayesianModelAverager(["a", "b"],
                                priors={"a": 0.5, "b": 0.5})
    avg.observe("a", math.log(0.9))
    avg.observe("b", math.log(0.4))
    # posterior ∝ (0.5*0.9, 0.5*0.4) = (0.45, 0.2)
    assert avg.posterior_weights() == pytest.approx({"a": 0.45 / 0.65,
                                                     "b": 0.20 / 0.65})


def test_evidence_accumulates_toward_the_better_member():
    avg = BayesianModelAverager(["sharp", "dull"])
    for _ in range(10):
        avg.observe_outcome("sharp", {"alpha": 0.9, "beta": 0.1},
                            "alpha")
        avg.observe_outcome("dull", {"alpha": 0.4, "beta": 0.6},
                            "alpha")
    post = avg.posterior_weights()
    assert post["sharp"] > 0.99
    assert post["dull"] < 0.01
    assert avg.observation_counts == {"sharp": 10, "dull": 10}


def test_custom_priors_respected():
    avg = BayesianModelAverager(["a", "b"],
                                priors={"a": 0.8, "b": 0.2})
    assert avg.posterior_weights() == pytest.approx({"a": 0.8, "b": 0.2})


def test_observe_outcome_returns_log_likelihood():
    avg = BayesianModelAverager(["a"])
    ll = avg.observe_outcome("a", {"alpha": 0.25, "beta": 0.75},
                             "beta")
    assert ll == pytest.approx(math.log(0.75))
    assert avg.log_evidences["a"] == pytest.approx(math.log(0.75))


def test_predictive_log_likelihood_exact_and_floored():
    assert predictive_log_likelihood({"x": 0.3}, "x") == pytest.approx(
        math.log(0.3))
    floored = predictive_log_likelihood({"x": 0.0}, "x")
    assert math.isfinite(floored)
    assert floored == pytest.approx(math.log(1e-12))
    missing = predictive_log_likelihood({}, "nope")
    assert math.isfinite(missing)


def test_bma_combine_matches_soft_when_uniform():
    avg = BayesianModelAverager(["a", "b"])
    result = bma_combine(_votes(), _ctx(fitted=avg))
    assert result.value == "alpha"
    # (0.8 + 0.3)/2 = 0.55
    assert result.probability == pytest.approx(0.55)
    assert result.metadata["ensemble"]["strategy"] == "bma"
    assert result.metadata["ensemble"]["posterior_weights"] == \
        pytest.approx({"a": 0.5, "b": 0.5})


def test_bma_combine_tilts_with_evidence():
    avg = BayesianModelAverager(["a", "b"])
    for _ in range(20):
        avg.observe_outcome("a", {"alpha": 0.9, "beta": 0.1}, "alpha")
        avg.observe_outcome("b", {"alpha": 0.1, "beta": 0.9}, "alpha")
    result = bma_combine(_votes(), _ctx(fitted=avg))
    assert result.value == "alpha"
    assert result.probability > 0.79  # ≈ posterior-weighted to a
    assert result.metadata["ensemble"]["posterior_weights"]["a"] > 0.99


def test_ensemble_end_to_end_with_attach():
    members = [ConstantBackend("a", "alpha",
                               {"alpha": 0.8, "beta": 0.2}),
               ConstantBackend("b", "beta",
                               {"alpha": 0.3, "beta": 0.7})]
    avg = BayesianModelAverager(["a", "b"])
    ens = Ensemble(members, strategy="bma").attach(avg)
    assert ens.fitted is avg
    result = ens.evaluate({"x": 1}, TWO)
    assert result.value == "alpha"
    assert result.backend == ens.name


def test_ensemble_constructor_fitted_kwarg():
    members = [ConstantBackend("a", "alpha",
                               {"alpha": 0.8, "beta": 0.2})]
    avg = BayesianModelAverager(["a"])
    ens = Ensemble(members, strategy="bma", fitted=avg)
    assert ens.evaluate({"x": 1}, TWO).value == "alpha"


def test_to_dict_reports_state():
    avg = BayesianModelAverager(["a", "b"], priors={"a": 0.7, "b": 0.3})
    d = avg.to_dict()
    assert d["members"] == ["a", "b"]
    assert d["priors"] == pytest.approx({"a": 0.7, "b": 0.3})
    assert d["posterior_weights"] == pytest.approx({"a": 0.7, "b": 0.3})


# --- failure -----------------------------------------------------------------

def test_bma_without_fitted_refuses_helpfully():
    with pytest.raises(BackendError, match="fitted BayesianModelAverager"):
        bma_combine(_votes(), _ctx())


def test_bma_with_wrong_fitted_type_refuses():
    with pytest.raises(BackendError, match="fitted BayesianModelAverager"):
        bma_combine(_votes(), _ctx(fitted={"not": "an averager"}))


def test_observe_unknown_member():
    avg = BayesianModelAverager(["a"])
    with pytest.raises(PolicyError, match="unknown member"):
        avg.observe("zzz", -1.0)


def test_bad_priors_rejected():
    with pytest.raises(PolicyError, match="unknown member"):
        BayesianModelAverager(["a"], priors={"zzz": 1.0})
    with pytest.raises(PolicyError, match=">= 0"):
        BayesianModelAverager(["a"], priors={"a": -0.5})
    with pytest.raises(PolicyError, match="positive"):
        BayesianModelAverager(["a", "b"],
                              priors={"a": 0.0, "b": 0.0})
    with pytest.raises(PolicyError, match="unique"):
        BayesianModelAverager(["a", "a"])
    with pytest.raises(PolicyError, match="at least one member"):
        BayesianModelAverager([])


def test_nonfinite_likelihood_rejected():
    avg = BayesianModelAverager(["a"])
    with pytest.raises(PolicyError, match="finite"):
        avg.observe("a", float("inf"))
    with pytest.raises(PolicyError, match="finite"):
        avg.observe("a", float("nan"))


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    avg = BayesianModelAverager(["a", "b"])
    with pytest.raises(BackendError, match="discrete spec"):
        bma_combine(_votes(), _ctx(spec=numeric, fitted=avg))


# --- boundary ----------------------------------------------------------------

def test_single_member_posterior_is_one():
    avg = BayesianModelAverager(["solo"])
    assert avg.posterior_weights() == {"solo": 1.0}
    votes = [MemberVote(backend="solo", value="alpha", probability=0.6,
                        distribution={"alpha": 0.6, "beta": 0.4},
                        weight=1.0)]
    result = bma_combine(votes, _ctx(fitted=avg))
    assert result.probability == pytest.approx(0.6)


def test_member_with_no_votes_gets_no_mass():
    # A member in the averager that cast no ballot contributes nothing.
    avg = BayesianModelAverager(["a", "b", "ghost"])
    result = bma_combine(_votes(), _ctx(fitted=avg))
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.55)
