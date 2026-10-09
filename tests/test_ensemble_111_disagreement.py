"""Slice 111 — Disagreement detection.

The DisagreementDetector turns ballot-diversity metrics into a
verdict (none / mild / strong) with dissenters named.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    LEVEL_MILD,
    LEVEL_NONE,
    LEVEL_STRONG,
    DisagreementDetector,
    DisagreementThresholds,
    Ensemble,
)
from hugrgate.ensemble.base import MemberVote
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _v(name, value):
    return MemberVote(backend=name, value=value, probability=0.6,
                      distribution={"alpha": 0.5, "beta": 0.5})


def _detector():
    return DisagreementDetector()


# --- success -----------------------------------------------------------------

def test_unanimous_is_none():
    report = _detector().detect([_v("a", "alpha"), _v("b", "alpha")])
    assert report.level == LEVEL_NONE
    assert report.disagree is False
    assert report.dissenters == []
    assert report.plurality_value == "alpha"
    assert report.ballots == 2


def test_two_to_one_split_is_strong():
    report = _detector().detect([_v("a", "alpha"), _v("b", "alpha"),
                                 _v("c", "beta")])
    # disagreement_rate = 2/3 >= 0.5 -> strong
    assert report.level == LEVEL_STRONG
    assert report.disagree is True
    assert report.dissenters == ["c"]
    assert report.plurality_value == "alpha"
    assert report.disagreement_rate == pytest.approx(2 / 3)


def test_four_to_one_split_is_mild():
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha"),
             _v("d", "alpha"), _v("e", "beta")]
    report = _detector().detect(votes)
    # disagreement_rate = 4/10 = 0.4 -> mild; entropy 0.72 -> mild
    assert report.level == LEVEL_MILD
    assert report.dissenters == ["e"]


def test_single_ballot_cannot_disagree():
    report = _detector().detect([_v("a", "alpha")])
    assert report.level == LEVEL_NONE
    assert report.disagree is False
    assert report.ballots == 1


def test_no_ballots_is_none():
    report = _detector().detect([])
    assert report.level == LEVEL_NONE
    assert report.plurality_value is None
    assert report.ballots == 0


def test_skipped_votes_excluded():
    votes = [_v("a", "alpha"), _v("b", "beta")]
    votes[1].skipped = True
    report = _detector().detect(votes)
    assert report.level == LEVEL_NONE
    assert report.ballots == 1


def test_custom_thresholds_change_verdict():
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha"),
             _v("d", "beta")]
    # rate = 3/6 = 0.5
    default = _detector().detect(votes)
    assert default.level == LEVEL_STRONG
    strict = DisagreementDetector(DisagreementThresholds(
        strong_disagreement=0.9, mild_disagreement=0.6,
        strong_entropy=2.0, mild_entropy=1.5, mild_margin=0.1))
    report = strict.detect(votes)
    assert report.level == LEVEL_NONE


def test_margin_rule_triggers_mild():
    # 3-1 split: rate 0.5, entropy 0.81, margin 0.5. With the rate and
    # entropy bars set high, only the close-margin rule fires -> mild.
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha"),
             _v("d", "beta")]
    detector = DisagreementDetector(DisagreementThresholds(
        strong_disagreement=0.9, mild_disagreement=0.9,
        strong_entropy=2.0, mild_entropy=2.0, mild_margin=0.6))
    report = detector.detect(votes)
    assert report.level == LEVEL_MILD
    assert report.winner_margin == pytest.approx(0.5)


def test_report_to_dict():
    report = _detector().detect([_v("a", "alpha"), _v("b", "beta")])
    d = report.to_dict()
    assert d["level"] == LEVEL_STRONG
    assert d["dissenters"] == ["b"]
    assert set(d) == {"level", "disagree", "vote_entropy",
                      "disagreement_rate", "winner_margin",
                      "plurality_value", "dissenters", "ballots"}


def test_end_to_end_with_ensemble_votes():
    ens = Ensemble([ConstantBackend("a", "alpha", ALPHA),
                    ConstantBackend("b", "alpha", ALPHA),
                    ConstantBackend("c", "beta", BETA)],
                   strategy="hard")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    report = _detector().detect(votes)
    assert report.level == LEVEL_STRONG
    assert report.dissenters == ["c"]


# --- failure -----------------------------------------------------------------

def test_threshold_validation():
    with pytest.raises(PolicyError, match="strong_disagreement must be >="):
        DisagreementThresholds(strong_disagreement=0.1,
                               mild_disagreement=0.5)
    with pytest.raises(PolicyError, match="strong_entropy must be >="):
        DisagreementThresholds(strong_entropy=0.1, mild_entropy=0.5)
    with pytest.raises(PolicyError, match="in \\[0,1\\]"):
        DisagreementThresholds(mild_disagreement=1.5)
    with pytest.raises(PolicyError, match=">= 0"):
        DisagreementThresholds(mild_margin=-0.1)


# --- boundary ----------------------------------------------------------------

def test_three_way_split_names_all_dissenters():
    votes = [_v("a", "alpha"), _v("b", "beta"), _v("c", "gamma")]
    report = _detector().detect(votes)
    assert report.level == LEVEL_STRONG
    # plurality breaks the 1-1-1 tie by earliest ballot -> "alpha"
    assert report.plurality_value == "alpha"
    assert report.dissenters == ["b", "c"]
