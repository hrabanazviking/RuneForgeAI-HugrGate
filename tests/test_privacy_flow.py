"""Slice 228 — Data-flow policy engine.

Tests the ordered rule evaluation: class eligibility, trust floor,
jurisdiction, field levels (deny vs redact modes), and local-only
stripping — plus adversarial flows that must be denied and the
DataFlowDenied error taxonomy registration.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import DataFlowDenied, HugrGateError, PrivacyViolation
from hugrgate.privacy_flow import (
    DataFlowPolicy,
    FlowDecision,
    FlowRequest,
)
from hugrgate.privacy_labels import Sensitivity


def req(**kw):
    base = dict(privacy_class="standard", dst_name="remote-llm",
                dst_remote=True, dst_trust="basic")
    base.update(kw)
    return FlowRequest(**base)


# -- happy paths -----------------------------------------------------------

def test_local_flow_always_passes():
    policy = DataFlowPolicy()
    decision = policy.check(FlowRequest(
        privacy_class="forbidden", dst_name="local",
        dst_remote=False, dst_trust="enclave",
        field_levels={"ssn": Sensitivity.SECRET}))
    assert decision.allowed and decision.action == "allow"


def test_standard_remote_allowed():
    decision = DataFlowPolicy().check(req())
    assert decision.allowed and decision.action == "allow"
    assert decision.reasons == ["all data-flow rules passed"]


def test_trusted_remote_for_strict():
    decision = DataFlowPolicy().check(req(privacy_class="strict",
                                          dst_trust="verified"))
    assert decision.allowed


def test_decision_serializes_policy():
    assert DataFlowPolicy(
        redact_instead_of_deny=True).to_dict() == \
        {"max_remote_level": "confidential", "redact_instead_of_deny": True}


# -- denials ----------------------------------------------------------------

def test_forbidden_class_never_remote():
    with pytest.raises(DataFlowDenied) as exc:
        DataFlowPolicy().check(req(privacy_class="forbidden",
                                   dst_trust="enclave"))
    assert "forbidden" in str(exc.value).lower()


def test_trust_floor_denies():
    with pytest.raises(DataFlowDenied) as exc:
        DataFlowPolicy().check(req(privacy_class="strict",
                                   dst_trust="basic"))
    assert "trust" in str(exc.value).lower()


def test_jurisdiction_denies():
    with pytest.raises(DataFlowDenied) as exc:
        DataFlowPolicy().check(req(dst_jurisdiction="US",
                                   jurisdictions_allowed={"EU"}))
    assert "jurisdiction" in str(exc.value).lower()


def test_local_jurisdiction_always_clean():
    decision = DataFlowPolicy().check(FlowRequest(
        privacy_class="standard", dst_name="local", dst_remote=False,
        jurisdictions_allowed={"EU"}))
    assert decision.allowed


def test_secret_field_denies_in_strict_mode():
    with pytest.raises(DataFlowDenied) as exc:
        DataFlowPolicy().check(req(field_levels={"ssn": "secret"}))
    assert "ssn" in str(exc.value)


def test_denied_decision_carries_reasons():
    try:
        DataFlowPolicy().check(req(privacy_class="forbidden"))
    except DataFlowDenied as e:
        assert e.details["reasons"]
        assert isinstance(e, PrivacyViolation)
        assert isinstance(e, HugrGateError)
        assert e.code == "data_flow_denied"
        assert e.recoverable is False
        # Wire round-trip keeps the exact class.
        rebuilt = HugrGateError.from_dict(e.to_dict())
        assert type(rebuilt) is DataFlowDenied
    else:  # pragma: no cover
        raise AssertionError("should have raised")


# -- redact mode --------------------------------------------------------------

def test_redact_mode_strips_over_clearance():
    policy = DataFlowPolicy(redact_instead_of_deny=True)
    decision = policy.check(req(field_levels={"ssn": "secret",
                                              "name": "public"}))
    assert decision.allowed and decision.action == "redact"
    assert decision.redactions == ["ssn"]


def test_local_only_always_stripped_remote():
    policy = DataFlowPolicy(redact_instead_of_deny=True)
    decision = policy.check(req(field_levels={"api_key": "internal"},
                                local_only_fields={"api_key"}))
    assert decision.action == "redact"
    assert decision.redactions == ["api_key"]


def test_local_only_kept_for_local_flow():
    policy = DataFlowPolicy()
    decision = policy.check(FlowRequest(
        privacy_class="standard", dst_name="local", dst_remote=False,
        field_levels={"api_key": "internal"},
        local_only_fields={"api_key"}))
    assert decision.action == "allow"
    assert decision.redactions == []


def test_hard_rules_deny_even_in_redact_mode():
    policy = DataFlowPolicy(redact_instead_of_deny=True)
    with pytest.raises(DataFlowDenied):
        policy.check(req(privacy_class="forbidden"))


# -- adversarial ----------------------------------------------------------------

def test_adversarial_trust_downgrade_attack():
    # Attacker-controlled metadata claims "enclave" trust for a remote
    # backend, but the request itself carries dst_remote=True with a
    # jurisdiction outside the allowed set — jurisdiction still denies.
    with pytest.raises(DataFlowDenied):
        DataFlowPolicy().check(req(dst_trust="enclave",
                                   dst_jurisdiction="XX",
                                   jurisdictions_allowed={"EU"}))


def test_unknown_privacy_class_rejected():
    with pytest.raises(ValueError):
        DataFlowPolicy().check(req(privacy_class="ultra-secret"))


def test_unknown_sensitivity_rejected():
    with pytest.raises(ValueError):
        FlowRequest(privacy_class="standard", dst_name="x",
                    field_levels={"f": "topsecret"})


def test_rule_order_is_deterministic():
    # A flow violating rules 1 AND 2 reports rule 1 (class eligibility)
    # first — deterministic ordering for explainability.
    policy = DataFlowPolicy()
    try:
        policy.check(req(privacy_class="forbidden", dst_trust="untrusted"))
    except DataFlowDenied as e:
        assert "forbids remote" in e.details["reasons"][0]
    else:  # pragma: no cover
        raise AssertionError("should have raised")


def test_raise_if_denied_returns_decision_when_allowed():
    decision = DataFlowPolicy().check(req())
    assert decision.raise_if_denied() is decision
    assert isinstance(decision, FlowDecision)
