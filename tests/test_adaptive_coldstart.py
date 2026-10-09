"""Slice 140 — cold-start routing tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.coldstart import ColdStartRouting
from hugrgate.adaptive.competence import BackendCompetenceProfiles
from hugrgate.errors import SpecError

NAMES = ["x0", "bias"]


def profiles_with_history():
    reg = BackendCompetenceProfiles()
    for _ in range(20):
        reg.observe("veteran", quality=0.9)
    for _ in range(2):
        reg.observe("newbie", quality=1.0)  # lucky but thin
    return reg


# --- success ---------------------------------------------------------------

def test_shrinkage_pulls_thin_history_toward_fleet():
    reg = profiles_with_history()
    cold = ColdStartRouting(reg, prior_strength=10.0)
    arms = ["veteran", "newbie"]
    shrunk_newbie = cold.shrunk_mean("newbie", arms)
    # Fleet mean = (20*0.9 + 2*1.0)/22 ≈ 0.909; shrunk newbie < 1.0.
    assert shrunk_newbie < 1.0
    assert shrunk_newbie > 0.9  # still above the veteran's 0.9
    # Veteran with 20 obs barely moves from its own 0.9:
    # (20*0.9 + 10*fleet) / 30 where fleet = 20/22 ≈ 0.909.
    assert cold.shrunk_mean("veteran", arms) == pytest.approx(
        (20 * 0.9 + 10 * (20.0 / 22)) / 30, rel=1e-6)

def test_zero_history_gets_fleet_prior():
    reg = BackendCompetenceProfiles()
    reg.observe("veteran", quality=0.8)
    cold = ColdStartRouting(reg)
    assert cold.shrunk_mean("brand_new", ["veteran", "brand_new"]) == \
        pytest.approx(0.8)

def test_no_history_anywhere_gets_neutral_prior():
    cold = ColdStartRouting(BackendCompetenceProfiles())
    assert cold.shrunk_mean("x", ["x"]) == 0.5

def test_recommend_prioritizes_maiden_voyages():
    reg = BackendCompetenceProfiles()
    for _ in range(50):
        reg.observe("incumbent", quality=0.99)
    cold = ColdStartRouting(reg, maiden_voyages=5)
    # The newcomer has no history but must get its first trials.
    assert cold.recommend(["incumbent", "newcomer"]) == "newcomer"
    assert cold.cold_arms(["incumbent", "newcomer"]) == ["newcomer"]

def test_recommend_graduates_cold_arms():
    reg = BackendCompetenceProfiles()
    for _ in range(10):
        reg.observe("a", quality=0.6)
        reg.observe("b", quality=0.9)
    cold = ColdStartRouting(reg, maiden_voyages=5)
    assert cold.recommend(["a", "b"]) == "b"
    assert cold.cold_arms(["a", "b"]) == []

def test_seed_bandit_gives_newcomer_a_fighting_chance():
    reg = BackendCompetenceProfiles()
    reg.observe("veteran", quality=0.9)
    cold = ColdStartRouting(reg)
    bandit = ContextualBanditAdapter(NAMES, alpha=0.0)
    used = cold.seed_bandit(bandit, ["veteran", "newcomer"])
    assert set(used) == {"veteran", "newcomer"}
    feats = {"x0": 1.0, "bias": 1.0}
    # Seeded priors: newcomer starts near fleet mean, not zero.
    assert bandit.expected_reward("newcomer", feats) > 0.0
    assert bandit.expected_reward("newcomer", feats) == pytest.approx(
        bandit.expected_reward("veteran", feats))

def test_prior_report_is_auditable():
    reg = profiles_with_history()
    cold = ColdStartRouting(reg)
    report = cold.prior_report(["veteran", "newbie"])
    by_arm = {r["arm"]: r for r in report}
    assert by_arm["newbie"]["is_cold"] is True
    assert by_arm["veteran"]["is_cold"] is False
    assert by_arm["newbie"]["attempts"] == 2
    assert by_arm["newbie"]["own_mean"] == pytest.approx(1.0)

# --- failure ---------------------------------------------------------------

def test_bad_constructor_args_rejected():
    with pytest.raises(SpecError):
        ColdStartRouting("not-profiles")
    with pytest.raises(SpecError):
        ColdStartRouting(BackendCompetenceProfiles(), prior_strength=0.0)
    with pytest.raises(SpecError):
        ColdStartRouting(BackendCompetenceProfiles(), maiden_voyages=0)

def test_recommend_needs_arms():
    with pytest.raises(SpecError):
        ColdStartRouting(BackendCompetenceProfiles()).recommend([])

def test_seed_bandit_needs_arms():
    with pytest.raises(SpecError):
        ColdStartRouting(BackendCompetenceProfiles()).seed_bandit(
            ContextualBanditAdapter(NAMES), [])
