"""Slice 113 — Consensus thresholds.

The winner's share must clear a configurable bar (majority,
supermajority, unanimity); otherwise the decision becomes an
abstention naming the shortfall.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend, make_result

from hugrgate.ensemble import (
    ConsensusConfig,
    Ensemble,
    apply_consensus,
    maybe_apply_consensus,
    winner_share,
)
from hugrgate.errors import PolicyError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _trio():
    return [ConstantBackend("a", "alpha", ALPHA),
            ConstantBackend("b", "alpha", ALPHA),
            ConstantBackend("c", "beta", BETA)]


# --- success -----------------------------------------------------------------

def test_majority_passes():
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    out = apply_consensus(result, CAT_SPEC(), ConsensusConfig.majority())
    assert out.accepted is True
    assert out.value == "alpha"
    assert out.metadata["ensemble"]["consensus"]["passed"] is True


def test_supermajority_boundary_is_inclusive():
    # 2/3 share meets the 2/3 bar exactly
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert winner_share(result) == pytest.approx(2 / 3)
    out = apply_consensus(result, CAT_SPEC(),
                          ConsensusConfig.supermajority())
    assert out.accepted is True


def test_supermajority_shortfall_abstains():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "beta", BETA),
               ConstantBackend("d", "beta", BETA),
               ConstantBackend("e", "beta", BETA)]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert winner_share(result) == pytest.approx(0.6)
    out = apply_consensus(result, CAT_SPEC(),
                          ConsensusConfig.supermajority())
    assert out.accepted is False
    assert out.value is None
    assert "consensus 0.600 below required agreement 0.667" in \
        out.metadata["abstain_reason"]
    assert out.metadata["ensemble"]["consensus"]["passed"] is False


def test_unanimity_requires_every_ballot():
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    out = apply_consensus(result, CAT_SPEC(),
                          ConsensusConfig.unanimity())
    assert out.accepted is False
    solo = Ensemble([ConstantBackend("a", "alpha", ALPHA)],
                    strategy="hard").evaluate({"x": 1}, CAT_SPEC())
    out = apply_consensus(solo, CAT_SPEC(), ConsensusConfig.unanimity())
    assert out.accepted is True


def test_ensemble_strategy_option_wires_the_gate():
    ens = Ensemble(_trio(), strategy="hard",
                   strategy_options={"consensus": 0.9})
    out = ens.evaluate({"x": 1}, CAT_SPEC())
    assert out.accepted is False
    assert "consensus" in out.metadata["abstain_reason"]
    # and without the option the same vote is accepted
    ens2 = Ensemble(_trio(), strategy="hard")
    assert ens2.evaluate({"x": 1}, CAT_SPEC()).accepted is True


def test_winner_share_falls_back_to_probability():
    result = make_result("alpha", ALPHA, "plain")
    assert "ensemble" not in result.metadata
    assert winner_share(result) == pytest.approx(0.7)
    out = apply_consensus(result, CAT_SPEC(), ConsensusConfig(0.8))
    assert out.accepted is False


def test_maybe_apply_consensus_forms():
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert maybe_apply_consensus(result, CAT_SPEC(), None) is result
    out = maybe_apply_consensus(result, CAT_SPEC(), 0.9)
    assert out.accepted is False
    out = maybe_apply_consensus(result, CAT_SPEC(),
                                ConsensusConfig(0.5))
    assert out.accepted is True
    out = maybe_apply_consensus(result, CAT_SPEC(),
                                {"min_agreement": 0.9})
    assert out.accepted is False


def test_presets():
    assert ConsensusConfig.majority().min_agreement == 0.5
    assert ConsensusConfig.supermajority().min_agreement == \
        pytest.approx(2 / 3)
    assert ConsensusConfig.unanimity().min_agreement == 1.0
    assert "0.5" in repr(ConsensusConfig.majority())


# --- failure -----------------------------------------------------------------

def test_bad_bars_rejected():
    with pytest.raises(PolicyError, match="in \\(0, 1\\]"):
        ConsensusConfig(0.0)
    with pytest.raises(PolicyError, match="in \\(0, 1\\]"):
        ConsensusConfig(1.5)
    with pytest.raises(PolicyError, match="in \\(0, 1\\]"):
        ConsensusConfig(-0.1)


def test_bad_setting_forms_rejected():
    result = Ensemble(_trio(), strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    with pytest.raises(PolicyError, match="must be a number"):
        maybe_apply_consensus(result, CAT_SPEC(), "high")
    with pytest.raises(PolicyError, match="must be a number"):
        maybe_apply_consensus(result, CAT_SPEC(), {"min_agreement": "x"})


# --- boundary ----------------------------------------------------------------

def test_consensus_with_soft_strategy_uses_mass():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1},
                                                         CAT_SPEC())
    # soft winner mass = (0.7+0.2)/2 = 0.45 < 0.5 majority
    out = apply_consensus(result, CAT_SPEC(), ConsensusConfig.majority())
    assert out.accepted is False
