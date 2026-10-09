"""Slice 114 — Minority-report preservation.

Dissent is data: every ensemble result preserves the dissenting
ballots, and audit_minority_report verifies the preservation is
complete and honest.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    Ensemble,
    MinorityReport,
    audit_minority_report,
    minority_report,
)
from hugrgate.ensemble.base import MemberVote
from ensemble_fakes import CAT_SPEC, ConstantBackend, make_result

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}
GAMMA = {"alpha": 0.1, "beta": 0.3, "gamma": 0.6}


def _trio():
    return [ConstantBackend("a", "alpha", ALPHA),
            ConstantBackend("b", "alpha", ALPHA),
            ConstantBackend("c", "beta", BETA)]


# --- success -----------------------------------------------------------------

def test_minority_report_extracts_dissent():
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    reports = minority_report(result)
    assert len(reports) == 1
    r = reports[0]
    assert isinstance(r, MinorityReport)
    assert r.backend == "c"
    assert r.value == "beta"
    assert r.probability == pytest.approx(0.6)
    assert "c" in r.to_text() and "beta" in r.to_text()


def test_unanimous_report_is_empty_but_present():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert minority_report(result) == []
    # the key exists even when empty: dissent can never be dropped
    assert "minority_report" in result.metadata["ensemble"]


def test_report_present_for_every_strategy():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    for strategy in ("soft", "hard", "weighted", "confidence"):
        result = Ensemble(members, strategy=strategy).evaluate(
            {"x": 1}, CAT_SPEC())
        assert "minority_report" in result.metadata["ensemble"]
        reports = minority_report(result)
        assert {r.backend for r in reports} <= {"a", "b"}


def test_audit_passes_on_faithful_report():
    ens = Ensemble(_trio(), strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    assert audit_minority_report(result, votes) == []


def test_audit_catches_missing_dissenter():
    ens = Ensemble(_trio(), strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    # tamper: drop the dissenter from the report
    result.metadata["ensemble"]["minority_report"] = []
    problems = audit_minority_report(result, votes)
    assert len(problems) == 1
    assert "c" in problems[0] and "missing" in problems[0]


def test_audit_catches_phantom_entry():
    ens = Ensemble([ConstantBackend("a", "alpha", ALPHA)],
                   strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    result.metadata["ensemble"]["minority_report"] = [
        {"backend": "ghost", "value": "beta", "probability": 0.5,
         "weight": 0.5}]
    problems = audit_minority_report(result, votes)
    assert len(problems) == 1
    assert "ghost" in problems[0] and "no matching" in problems[0]


def test_audit_catches_value_mismatch():
    ens = Ensemble(_trio(), strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    result.metadata["ensemble"]["minority_report"][0]["value"] = "gamma"
    problems = audit_minority_report(result, votes)
    assert len(problems) == 1
    assert "but the ballot was" in problems[0]


def test_audit_skips_abstentions():
    result = make_result("alpha", ALPHA, "trio")
    result.value = None
    votes = [MemberVote(backend="a", value="alpha", probability=0.7,
                        distribution=dict(ALPHA))]
    assert audit_minority_report(result, votes) == []


def test_audit_ignores_skipped_votes():
    ens = Ensemble(_trio(), strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    votes[2].skipped = True  # the dissenter "didn't vote"
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    # report still names c (it did vote in evaluate); audit against
    # the doctored vote list flags nothing missing, but the phantom
    # check uses the same list -> c has no ballot -> phantom problem
    problems = audit_minority_report(result, votes)
    assert any("no matching" in p for p in problems)


# --- boundary -----------------------------------------------------------------

def test_report_survives_escalation_abstain():
    from hugrgate.ensemble import (
        DisagreementDetector,
        EscalationPolicy,
        escalate,
    )
    ens = Ensemble(_trio(), strategy="hard")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    report = DisagreementDetector().detect(
        ens.member_votes({"x": 1}, CAT_SPEC()))
    out = escalate(result, CAT_SPEC(), report,
                   EscalationPolicy(strong_action="abstain"))
    # abstentions have no winner: audit is a no-op, extraction is []
    assert minority_report(out) == []
    assert audit_minority_report(out, ens.member_votes({"x": 1},
                                                      CAT_SPEC())) == []
