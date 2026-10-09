"""Slice 060 — privacy-aware routing v2 (incl. adversarial tests)."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    BackendClearance,
    DataClassifier,
    DynamicRungPlanner,
    LadderRouterV2,
    PrivacyAwarePlanner,
    PrivacyTier,
    RouterContext,
)


class PrivBackend(Backend):
    def __init__(self, name, prob=0.95, remote=False, data_retained=False):
        self.name = name
        self._prob = prob
        self.is_remote = remote
        self._retained = data_retained

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type in self._spec_types if hasattr(
            self, "_spec_types") else spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def privacy_properties(self):
        return {"remote": self.is_remote,
                "data_retained": self._retained}


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec(tier=None):
    meta = {"data_tier": tier} if tier else {}
    return DecisionSpec(type="categorical", options=["a", "b"],
                        metadata=meta)


def ctx(state, policy=None, spec_obj=None):
    return RouterContext.from_request(state, spec_obj or spec(),
                                      policy or DecisionPolicy())


# -- classifier --------------------------------------------------------------------

def test_key_classification():
    c = DataClassifier()
    assert c.classify_key("ssn") is PrivacyTier.RESTRICTED
    assert c.classify_key("user_password_hash") is PrivacyTier.RESTRICTED
    assert c.classify_key("email") is PrivacyTier.CONFIDENTIAL
    assert c.classify_key("phone_number") is PrivacyTier.CONFIDENTIAL
    assert c.classify_key("internal_notes") is PrivacyTier.INTERNAL
    assert c.classify_key("favorite_color") is PrivacyTier.PUBLIC
    assert c.classify(ctx({"favorite_color": "blue"})) is PrivacyTier.PUBLIC
    assert c.classify(ctx({"ssn": "x", "email": "y"})) is PrivacyTier.RESTRICTED


def test_extra_rules_and_override():
    c = DataClassifier(extra_rules={"project_phoenix": PrivacyTier.RESTRICTED})
    assert c.classify(ctx({"project_phoenix_plan": 1})) is PrivacyTier.RESTRICTED
    assert c.classify(ctx({"a": 1}, spec_obj=spec("confidential"))) is \
        PrivacyTier.CONFIDENTIAL
    with pytest.raises(ValueError):
        c.classify(ctx({"a": 1}, spec_obj=spec("cosmic")))


def test_strict_policy_floors_tier():
    c = DataClassifier()
    plain = ctx({"favorite_color": "blue"})
    strict = ctx({"favorite_color": "blue"},
                 DecisionPolicy(privacy_class="strict"))
    assert c.classify(plain) is PrivacyTier.PUBLIC
    assert c.classify(strict) is PrivacyTier.CONFIDENTIAL


# -- clearance -----------------------------------------------------------------------

def test_clearance_grades():
    assert BackendClearance.clearance(
        PrivBackend("local")) is PrivacyTier.RESTRICTED
    assert BackendClearance.clearance(
        PrivBackend("cloud", remote=True)) is PrivacyTier.INTERNAL
    assert BackendClearance.clearance(
        PrivBackend("logger", data_retained=True)) is PrivacyTier.INTERNAL
    assert BackendClearance.clearance(
        PrivBackend("spy", remote=True,
                    data_retained=True)) is PrivacyTier.PUBLIC


# -- planner ---------------------------------------------------------------------------

def test_planner_prunes_by_tier():
    reg = reg_of(PrivBackend("local"), PrivBackend("cloud", remote=True))
    planner = PrivacyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx({"ssn": "123"}, DecisionPolicy(
        remote_inference=True)))
    assert [n.backend_name for n in plan.nodes] == ["local"]
    assert any("pruned 1" in r for r in plan.rationale)
    assert plan.nodes[0].params["privacy_tier"] == "restricted"


def test_public_data_reaches_remote():
    reg = reg_of(PrivBackend("cloud", remote=True))
    planner = PrivacyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx({"favorite_color": "blue"},
                            DecisionPolicy(remote_inference=True)))
    assert [n.backend_name for n in plan.nodes] == ["cloud"]


# -- adversarial --------------------------------------------------------------------------

def test_adversarial_remote_exfiltration_of_ssn_blocked():
    """A remote backend must never see RESTRICTED data, even when the
    policy allows remote inference."""
    reg = reg_of(PrivBackend("cloud", remote=True, prob=0.99))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("cloud")]},
        planner=PrivacyAwarePlanner(DynamicRungPlanner(reg), reg))
    with pytest.raises(Abstention):
        router.decide({"ssn": "123-45-6789"}, spec(),
                      DecisionPolicy(remote_inference=True))


def test_adversarial_retaining_backend_blocked_for_confidential():
    reg = reg_of(PrivBackend("logger", data_retained=True, prob=0.99))
    planner = PrivacyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx({"email": "a@b.c"}))
    assert plan.nodes == []  # CONFIDENTIAL > INTERNAL clearance


def test_adversarial_strict_policy_blocks_remote_entirely():
    reg = reg_of(PrivBackend("cloud", remote=True, prob=0.99))
    planner = PrivacyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx({"note": "hello"},
                            DecisionPolicy(privacy_class="strict",
                                           remote_inference=True)))
    # strict floors tier to CONFIDENTIAL; remote clearance is INTERNAL
    assert plan.nodes == []


def test_adversarial_spoofed_local_claim_still_caught():
    """A backend claiming local while its privacy properties say remote
    is graded by properties, not by the flag alone."""

    class Spoof(PrivBackend):
        @property
        def is_remote(self):
            return False

        @is_remote.setter
        def is_remote(self, value):
            pass

        def privacy_properties(self):
            return {"remote": True, "data_retained": False}

    reg = reg_of(Spoof("spoof"))
    planner = PrivacyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx({"ssn": "x"}))
    assert plan.nodes == []


def test_local_no_retain_serves_restricted_end_to_end():
    reg = reg_of(PrivBackend("local", prob=0.99))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("local")]},
        planner=PrivacyAwarePlanner(DynamicRungPlanner(reg), reg))
    won = router.decide({"ssn": "123-45-6789"}, spec(),
                        DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "local"
