"""Slice 135 — privacy-constrained objective tests.

Includes adversarial tests: the gate must reject forbidden arms even
when the advisory ``privacy_ok`` flag claims otherwise, and even when
the wrapped objective would score them highest.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy
from hugrgate.adaptive.cost_quality import (
    CostQualityObjective,
    RoutingCandidate,
)
from hugrgate.adaptive.privacy_objective import PrivacyConstrainedObjective
from hugrgate.errors import BackendUnavailable, SpecError


def local(name="local", quality=0.7):
    return RoutingCandidate(name=name, quality=quality, cost=0.1,
                            latency_ms=100.0, energy_wh=0.01,
                            is_remote=False, data_retained=False)


def remote(name="remote", quality=0.99):
    # Higher quality than local: without the gate it would win.
    return RoutingCandidate(name=name, quality=quality, cost=0.1,
                            latency_ms=50.0, energy_wh=0.005,
                            is_remote=True, data_retained=False)


def retaining(name="retainer", quality=0.95):
    return RoutingCandidate(name=name, quality=quality, cost=0.1,
                            latency_ms=50.0, energy_wh=0.005,
                            is_remote=False, data_retained=True)


def strict_policy(**kw):
    params = dict(privacy_class="strict")
    params.update(kw)
    return DecisionPolicy(**params)


# --- success ---------------------------------------------------------------

def test_permitted_arms_score_normally():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    assert obj.permitted(local()) is True
    assert obj.score(local()) == CostQualityObjective().score(local())

def test_admissible_filters_to_permitted_subset():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    cands = [remote(), local(), retaining()]
    assert [c.name for c in obj.admissible(cands)] == ["local"]

def test_best_picks_highest_scoring_admissible():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    a = local("a", quality=0.6)
    b = local("b", quality=0.9)
    assert obj.best([a, b, remote()]).name == "b"

def test_standard_policy_permits_remote_when_policy_allows():
    policy = DecisionPolicy(privacy_class="standard", remote_inference=True)
    obj = PrivacyConstrainedObjective(CostQualityObjective(), policy)
    assert obj.permitted(remote()) is True
    # ...but the policy's own remote flag still gates.
    policy2 = DecisionPolicy(privacy_class="standard",
                             remote_inference=False)
    obj2 = PrivacyConstrainedObjective(CostQualityObjective(), policy2)
    assert obj2.permitted(remote()) is False

def test_allowed_list_respected():
    obj = PrivacyConstrainedObjective(
        CostQualityObjective(), strict_policy(allowed_backends=["local"]))
    assert obj.permitted(local("local")) is True
    assert obj.permitted(local("other")) is False

def test_to_dict_names_wrapped_objective():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    d = obj.to_dict()
    assert d["name"] == "privacy_constrained"
    assert d["objective"] == "cost_quality"
    assert d["privacy_class"] == "strict"

# --- failure: nothing admissible -------------------------------------------

def test_no_admissible_arm_raises_backend_unavailable():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    with pytest.raises(BackendUnavailable):
        obj.require_admissible([remote(), retaining()])
    with pytest.raises(BackendUnavailable):
        obj.best([remote()])

# --- adversarial -----------------------------------------------------------

def test_privacy_ok_flag_is_not_trusted():
    # A compromised estimator sets privacy_ok=True on a remote arm.
    sneaky = RoutingCandidate(name="sneaky", quality=0.99, cost=0.0,
                              latency_ms=10.0, energy_wh=0.0,
                              privacy_ok=True, is_remote=True)
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    assert sneaky.privacy_ok is True  # the lie is in place...
    assert obj.permitted(sneaky) is False  # ...and the gate ignores it
    assert obj.score(sneaky) == float("-inf")

def test_data_retention_blocked_even_when_local():
    obj = PrivacyConstrainedObjective(CostQualityObjective(),
                                      strict_policy())
    assert obj.permitted(retaining()) is False

def test_strict_gate_cannot_be_bypassed_via_high_score():
    obj = PrivacyConstrainedObjective(CostQualityObjective(), strict_policy())
    cands = [remote("r", quality=1.0), local("l", quality=0.01)]
    # The remote arm has the best raw score by far; the gate still wins.
    assert CostQualityObjective().score(cands[0]) > \
        CostQualityObjective().score(cands[1])
    assert obj.best(cands).name == "l"

def test_inadmissible_scores_negative_infinity():
    obj = PrivacyConstrainedObjective(CostQualityObjective(), strict_policy())
    assert obj.score(remote()) == float("-inf")

def test_constructor_validates_types():
    with pytest.raises(SpecError):
        PrivacyConstrainedObjective("not-an-objective", strict_policy())
    with pytest.raises(SpecError):
        PrivacyConstrainedObjective(CostQualityObjective(), "not-a-policy")
