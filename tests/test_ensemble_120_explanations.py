"""Slice 120 — Ensemble explanations.

Every claim in the rendered text must be traceable to the recorded
metadata: the explanation can never drift from the decision.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import Ensemble, explain_ensemble
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _result(strategy="weighted"):
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "beta", BETA)]
    ens = Ensemble(members, strategy=strategy,
                   weights={"a": 1.0, "b": 1.0, "c": 1.0})
    return ens.evaluate({"x": 1}, CAT_SPEC())


# --- success -----------------------------------------------------------------

def test_concise_names_verdict_votes_and_dissent():
    text = explain_ensemble(_result())
    assert "chose 'alpha'" in text
    assert "weighted voting" in text
    assert "67%" in text                     # probability + share
    assert "3 of 3 member ballots counted" in text
    assert "c voted 'beta'" in text           # the dissenter


def test_concise_unanimous_has_no_dissent():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    ens = Ensemble(members, strategy="hard")
    text = explain_ensemble(ens.evaluate({"x": 1}, CAT_SPEC()))
    assert "Dissent" not in text
    assert "chose 'alpha'" in text


def test_verbose_lists_ballots_and_minority_report():
    text = explain_ensemble(_result(), style="verbose")
    assert text.startswith("Verdict: 'alpha'")
    assert "- a: voted 'alpha' (confidence 0.70, weight 0.33)" in text
    assert "- c: voted 'beta' (confidence 0.60, weight 0.33)" in text
    assert "Minority report:" in text
    assert "- c dissented with 'beta'" in text


def test_verbose_unanimous_says_so():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    ens = Ensemble(members, strategy="hard")
    text = explain_ensemble(ens.evaluate({"x": 1}, CAT_SPEC()),
                            style="verbose")
    assert "unanimous — no dissenters" in text


def test_explanation_narrates_consensus_failure():
    from hugrgate.ensemble import ConsensusConfig, maybe_apply_consensus
    result = maybe_apply_consensus(
        _result(), CAT_SPEC(),
        ConsensusConfig(min_agreement=0.99))  # 2/3 < 0.99 -> abstain
    assert result.value is None
    text = explain_ensemble(result)
    assert "declined to decide" in text
    assert "failed the consensus bar" in text


def test_explanation_narrates_disagreement_escalation():
    from hugrgate.ensemble import (DisagreementDetector, EscalationPolicy,
                                   escalate)
    from hugrgate.ensemble.base import collect_votes
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="hard")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    votes = collect_votes(members, {"x": 1}, CAT_SPEC())
    report = DisagreementDetector().detect(votes)
    out = escalate(result, CAT_SPEC(), report,
                   EscalationPolicy(mild_action="review",
                                    strong_action="review"))
    text = explain_ensemble(out)
    assert f"disagreement was {report.level}" in text
    assert "flagged for human review" in text


def test_explanation_notes_calibration():
    from hugrgate.ensemble import EnsembleCalibrator
    result = _result()
    cal = EnsembleCalibrator().fit(
        [dict(result.distribution)] * 10,
        ["alpha"] * 6 + ["beta"] * 4,
        ["alpha", "beta", "gamma"])
    out = cal.calibrate_result(result)
    text = explain_ensemble(out)
    assert "temperature-calibrated" in text
    assert f"T={cal.temperature:.2f}" in text


# --- failure -----------------------------------------------------------------

def test_non_ensemble_result_rejected():
    backend = ConstantBackend("solo", "alpha", ALPHA)
    result = backend.evaluate({"x": 1}, CAT_SPEC())
    with pytest.raises(PolicyError, match="no ensemble metadata"):
        explain_ensemble(result)


def test_provenance_marked_non_ensemble_rejected():
    from hugrgate.result import DecisionResult
    result = DecisionResult(
        value="alpha", probability=0.9,
        distribution={"alpha": 0.9, "beta": 0.1},
        metadata={"ensemble": {"recorded": False}})
    with pytest.raises(PolicyError, match="not an ensemble"):
        explain_ensemble(result)


def test_unknown_style_rejected():
    with pytest.raises(PolicyError, match="style must be"):
        explain_ensemble(_result(), style="poetic")


# --- boundary -----------------------------------------------------------------

def test_abstention_without_reason_still_explains():
    from hugrgate.abstain import abstain
    out = abstain(CAT_SPEC(), reason="quiet", backend="ensemble[x]",
                  metadata={"ensemble": {"strategy": "hard",
                                         "members": ["a"],
                                         "member_votes": [],
                                         "weights": {},
                                         "winner_share": 0.0,
                                         "minority_report": [],
                                         "usable_votes": 0,
                                         "skipped_votes": 1}})
    text = explain_ensemble(out)
    assert text.startswith("The council declined to decide.")
    assert "1 member ballot(s) skipped" in text
