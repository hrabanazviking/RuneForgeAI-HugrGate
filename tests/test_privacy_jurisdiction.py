"""Slice 230 — Jurisdiction metadata.

Tests jurisdiction defaults (local/unknown), declarations, the
JurisdictionPolicy allow-set, guard integration (selection +
attempt), and adversarial cases (undeclared remotes fail closed,
local backends always pass).
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import (
    HugrGateError,
    JurisdictionViolation,
    PrivacyViolation,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_jurisdiction import (
    LOCAL_JURISDICTION,
    UNKNOWN_JURISDICTION,
    JurisdictionPolicy,
    JurisdictionRegistry,
)
from hugrgate.result import DecisionResult


class FakeBackend(Backend):
    def __init__(self, name: str, remote: bool = False):
        self.name = name
        self.is_remote = remote

    def capabilities(self):
        return {}

    def supports(self, spec):
        return True

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0})


LOCAL = FakeBackend("local-ml")
EU_REMOTE = FakeBackend("eu-llm", remote=True)
US_REMOTE = FakeBackend("us-llm", remote=True)
MYSTERY_REMOTE = FakeBackend("mystery", remote=True)


@pytest.fixture
def registry():
    reg = JurisdictionRegistry()
    reg.declare("eu-llm", "EU")
    reg.declare("us-llm", "US")
    return reg


def test_defaults(registry):
    assert registry.jurisdiction_for(LOCAL) == LOCAL_JURISDICTION
    assert registry.jurisdiction_for(EU_REMOTE) == "EU"
    # Undeclared remote: fail-closed "unknown".
    assert registry.jurisdiction_for(MYSTERY_REMOTE) == UNKNOWN_JURISDICTION


def test_declare_updates():
    reg = JurisdictionRegistry()
    reg.declare("mystery", "EU")
    assert reg.jurisdiction_for(MYSTERY_REMOTE) == "EU"


def test_policy_allows_listed(registry):
    policy = JurisdictionPolicy(allowed={"EU"}, registry=registry)
    assert policy.check(EU_REMOTE) == "EU"


def test_policy_denies_unlisted(registry):
    policy = JurisdictionPolicy(allowed={"EU"}, registry=registry)
    with pytest.raises(JurisdictionViolation) as exc:
        policy.check(US_REMOTE)
    assert exc.value.details["jurisdiction"] == "US"
    assert isinstance(exc.value, PrivacyViolation)


def test_policy_denies_unknown_by_default(registry):
    # Adversarial: an undeclared remote backend under an allow-set is
    # denied — fail closed, not fail open.
    policy = JurisdictionPolicy(allowed={"EU"}, registry=registry)
    with pytest.raises(JurisdictionViolation):
        policy.check(MYSTERY_REMOTE)


def test_local_always_passes(registry):
    policy = JurisdictionPolicy(allowed={"EU"}, registry=registry)
    assert policy.check(LOCAL) == "local"


def test_no_restriction_allows_all(registry):
    policy = JurisdictionPolicy(registry=registry)
    assert policy.check(US_REMOTE) == "US"
    assert policy.check(MYSTERY_REMOTE) == UNKNOWN_JURISDICTION


def test_policy_round_trip(registry):
    policy = JurisdictionPolicy(allowed={"EU", "US"}, registry=registry)
    rebuilt = JurisdictionPolicy.from_dict(policy.to_dict())
    assert rebuilt.allowed == {"EU", "US"}
    assert rebuilt.registry.jurisdiction_for(EU_REMOTE) == "EU"


def test_guard_enforces_jurisdiction(registry):
    guard = PrivacyGuard(jurisdiction_registry=registry,
                         jurisdictions_allowed={"EU"})
    policy = DecisionPolicy(remote_inference=True)
    assert guard.remote_allowed(EU_REMOTE, policy) is True
    assert guard.remote_allowed(US_REMOTE, policy) is False
    assert guard.remote_allowed(MYSTERY_REMOTE, policy) is False
    assert guard.remote_allowed(LOCAL, policy) is True
    guard.check_backend(EU_REMOTE, policy)  # no raise
    with pytest.raises(JurisdictionViolation):
        guard.check_backend(US_REMOTE, policy)


def test_guard_filter_backends(registry):
    guard = PrivacyGuard(jurisdiction_registry=registry,
                         jurisdictions_allowed={"EU"})
    policy = DecisionPolicy(remote_inference=True)
    names = [b.name for b in guard.filter_backends(
        [LOCAL, EU_REMOTE, US_REMOTE, MYSTERY_REMOTE], policy)]
    assert names == ["local-ml", "eu-llm"]


def test_guard_without_allow_set_is_unrestricted():
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True)
    assert guard.remote_allowed(MYSTERY_REMOTE, policy) is True


def test_violation_taxonomy_and_wire():
    err = JurisdictionViolation("crossed", backend="x",
                                jurisdiction="US")
    assert err.code == "jurisdiction_violation"
    assert err.recoverable is False
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert type(rebuilt) is JurisdictionViolation
    assert rebuilt.details["jurisdiction"] == "US"
