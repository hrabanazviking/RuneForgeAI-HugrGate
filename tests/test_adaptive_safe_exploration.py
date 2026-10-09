"""Slice 142 — safe exploration tests."""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy
from hugrgate.adaptive.cost_quality import RoutingCandidate
from hugrgate.adaptive.exploration import (
    ExplorationConfig,
    ExplorationControls,
)
from hugrgate.adaptive.safe_exploration import SafeChoice, SafeExploration
from hugrgate.errors import BackendUnavailable, SpecError


def cand(name, is_remote=False, data_retained=False, latency_ms=100.0,
         cost=0.1):
    return RoutingCandidate(name=name, quality=0.8, cost=cost,
                            latency_ms=latency_ms, energy_wh=0.01,
                            is_remote=is_remote,
                            data_retained=data_retained)


CANDS = [cand("local_a"), cand("local_b"), cand("remote_x", is_remote=True)]


def explorer(**cfg_kw):
    params = {"min_pulls_per_arm": 0}
    params.update(cfg_kw)
    if params.get("epsilon", 0.1) == 0.0 and "epsilon_min" not in params:
        params["epsilon_min"] = 0.0
    return SafeExploration(
        ExplorationControls(ExplorationConfig(**params), seed=7), seed=7)


# --- success ---------------------------------------------------------------

def test_eligible_filters_remote_under_strict():
    policy = DecisionPolicy(privacy_class="strict")
    safe = explorer()
    eligible = safe.eligible(CANDS, policy)
    assert [c.name for c in eligible] == ["local_a", "local_b"]

def test_eligible_respects_allowed_list_latency_and_cost():
    policy = DecisionPolicy(allowed_backends=["local_a", "remote_x"],
                            maximum_latency_ms=50.0, max_cost=0.05)
    safe = explorer()
    # local_a: latency 100 > 50 -> out; remote_x: cost 0.1 > 0.05 -> out.
    assert safe.eligible(CANDS, policy) == []
    with pytest.raises(BackendUnavailable):
        safe.require_eligible(CANDS, policy)

def test_explore_choice_never_leaves_eligible_set():
    policy = DecisionPolicy(privacy_class="strict")
    safe = explorer(epsilon=1.0)  # always explore when asked
    seen = set()
    for _ in range(50):
        choice = safe.choose(CANDS, policy, exploit_arm="local_a",
                             arm_pulls={"local_a": 100, "local_b": 100,
                                        "remote_x": 100})
        assert isinstance(choice, SafeChoice)
        seen.add(choice.arm)
        assert choice.arm in ("local_a", "local_b")  # never remote_x
    assert seen == {"local_a", "local_b"}  # both get explored

def test_explore_never_repulls_exploit_arm():
    policy = DecisionPolicy()
    safe = explorer(epsilon=1.0)
    for _ in range(20):
        choice = safe.choose(CANDS, policy, exploit_arm="local_a",
                             arm_pulls={n: 100 for n in
                                        ("local_a", "local_b", "remote_x")})
        if choice.explored:
            assert choice.arm != "local_a"

def test_exploit_path_returns_incumbent():
    policy = DecisionPolicy()  # remote_inference=False by default
    safe = explorer(epsilon=0.0)
    choice = safe.choose(CANDS, policy, exploit_arm="local_b",
                         arm_pulls={"local_a": 10, "local_b": 10,
                                    "remote_x": 10})
    assert choice.arm == "local_b" and choice.explored is False
    assert choice.eligible_arms == ["local_a", "local_b"]

def test_data_retaining_arm_excluded_under_strict():
    policy = DecisionPolicy(privacy_class="strict")
    safe = explorer()
    cands = [cand("keeper", data_retained=True), cand("clean")]
    assert [c.name for c in safe.eligible(cands, policy)] == ["clean"]

# --- failure ---------------------------------------------------------------

def test_no_eligible_arms_fails_closed():
    policy = DecisionPolicy(privacy_class="strict",
                            allowed_backends=["remote_x"])
    safe = explorer()
    with pytest.raises(BackendUnavailable):
        safe.choose(CANDS, policy, exploit_arm="local_a", arm_pulls={})

def test_ineligible_exploit_arm_rejected():
    policy = DecisionPolicy(privacy_class="strict")
    safe = explorer()
    with pytest.raises(SpecError):
        safe.choose(CANDS, policy, exploit_arm="remote_x", arm_pulls={})

def test_bad_types_rejected():
    with pytest.raises(SpecError):
        SafeExploration("not-controls")
    with pytest.raises(SpecError):
        explorer().eligible(CANDS, "not-a-policy")
