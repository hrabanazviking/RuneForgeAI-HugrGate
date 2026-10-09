"""Slice 112 — Disagreement escalation.

When members disagree, the EscalationPolicy decides: decide anyway,
flag for human review, abstain with a named reason, or fall back to
a designated backend.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import (
    CAT_SPEC,
    ConstantBackend,
    FailingBackend,
    make_result,
)

from hugrgate.ensemble import (
    LEVEL_MILD,
    LEVEL_NONE,
    LEVEL_STRONG,
    DisagreementDetector,
    Ensemble,
    EscalationPolicy,
    escalate,
)
from hugrgate.ensemble.base import MemberVote
from hugrgate.errors import BackendError, PolicyError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _v(name, value):
    return MemberVote(backend=name, value=value, probability=0.6,
                      distribution={"alpha": 0.5, "beta": 0.5})


def _strong_report():
    return DisagreementDetector().detect(
        [_v("a", "alpha"), _v("b", "alpha"), _v("c", "beta")])


def _mild_report():
    return DisagreementDetector().detect(
        [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha"),
         _v("d", "alpha"), _v("e", "beta")])


def _none_report():
    return DisagreementDetector().detect(
        [_v("a", "alpha"), _v("b", "alpha")])


def _result():
    return make_result("alpha", ALPHA, "trio")


# --- success -----------------------------------------------------------------

def test_none_level_passes_through():
    policy = EscalationPolicy(mild_action="abstain",
                              strong_action="abstain")
    out = escalate(_result(), CAT_SPEC(), _none_report(), policy)
    assert out.accepted is True
    assert out.value == "alpha"
    assert out.metadata["ensemble"]["disagreement"]["level"] == LEVEL_NONE


def test_mild_review_flags_result():
    policy = EscalationPolicy(mild_action="review",
                              strong_action="review")
    out = escalate(_result(), CAT_SPEC(), _mild_report(), policy)
    assert out.accepted is False
    assert out.value == "alpha"  # value preserved, flagged
    assert out.metadata["policy_verdict"] == "review"
    assert "disagreement (mild)" in out.metadata["review_reason"]
    assert out.metadata["ensemble"]["disagreement"]["level"] == LEVEL_MILD


def test_strong_abstain_refuses_with_reason():
    policy = EscalationPolicy(strong_action="abstain")
    out = escalate(_result(), CAT_SPEC(), _strong_report(), policy)
    assert out.accepted is False
    assert out.value is None
    assert "disagreement (strong)" in out.metadata["abstain_reason"]
    assert out.metadata["ensemble"]["disagreement"]["dissenters"] == ["c"]


def test_strong_fallback_uses_fallback_backend():
    fb = ConstantBackend("fallback", "beta", BETA)
    policy = EscalationPolicy(strong_action="fallback",
                              fallback_backend=fb)
    out = escalate(_result(), CAT_SPEC(), _strong_report(), policy,
                   state={"x": 1})
    assert out.value == "beta"
    assert out.fallback_used is True
    assert "disagreement (strong)" in out.metadata["disagreement_fallback"]


def test_mild_action_none_decides_anyway():
    policy = EscalationPolicy(mild_action="none",
                              strong_action="abstain")
    out = escalate(_result(), CAT_SPEC(), _mild_report(), policy)
    assert out.accepted is True
    assert out.value == "alpha"


def test_end_to_end_ensemble_detect_escalate():
    ens = Ensemble([ConstantBackend("a", "alpha", ALPHA),
                    ConstantBackend("b", "alpha", ALPHA),
                    ConstantBackend("c", "beta", BETA)],
                   strategy="hard")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    report = DisagreementDetector().detect(
        ens.member_votes({"x": 1}, CAT_SPEC()))
    assert report.level == LEVEL_STRONG
    out = escalate(result, CAT_SPEC(), report,
                   EscalationPolicy(strong_action="review"))
    assert out.accepted is False
    assert out.metadata["policy_verdict"] == "review"


# --- failure -----------------------------------------------------------------

def test_fallback_failure_raises_honestly():
    policy = EscalationPolicy(strong_action="fallback",
                              fallback_backend=FailingBackend("bad"))
    with pytest.raises(BackendError, match="fallback backend"):
        escalate(_result(), CAT_SPEC(), _strong_report(), policy,
                 state={"x": 1})


def test_policy_validation():
    with pytest.raises(PolicyError, match="mild_action"):
        EscalationPolicy(mild_action="panic")
    with pytest.raises(PolicyError, match="strong_action"):
        EscalationPolicy(strong_action="panic")
    with pytest.raises(PolicyError, match="fallback_backend"):
        EscalationPolicy(strong_action="fallback")
    with pytest.raises(PolicyError, match="fallback_backend"):
        EscalationPolicy(mild_action="fallback")


# --- boundary ----------------------------------------------------------------

def test_disagreement_report_lands_in_ensemble_metadata():
    # escalate always records the report under metadata["ensemble"],
    # even for results that carry no ensemble block of their own.
    for policy, report in [
        (EscalationPolicy(mild_action="review"), _mild_report()),
        (EscalationPolicy(strong_action="abstain"), _strong_report()),
    ]:
        out = escalate(_result(), CAT_SPEC(), report, policy)
        assert out.metadata["ensemble"]["disagreement"]["level"] == \
            report.level
