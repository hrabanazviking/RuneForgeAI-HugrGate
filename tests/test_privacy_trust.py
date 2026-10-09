"""Slice 229 — Backend trust levels.

Tests the attested trust registry (attest/revoke/expiry/fallback),
guard integration (attested remotes can carry strict data; revoked
ones cannot), and adversarial cases (expired attestation, wrong-name
attestation, unknown levels).
"""

from __future__ import annotations

import time

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import PrivacyViolation
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard, default_trust_level, trust_rank
from hugrgate.privacy_trust import BackendTrustRegistry, TrustAttestation
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


REMOTE = FakeBackend("remote-llm", remote=True)
LOCAL = FakeBackend("local-ml")


def test_defaults_without_registry():
    registry = BackendTrustRegistry()
    assert registry.level_for(REMOTE) == "basic"
    assert registry.level_for(LOCAL) == "enclave"
    assert registry.meets(REMOTE, "basic")
    assert not registry.meets(REMOTE, "verified")


def test_attest_and_meets():
    registry = BackendTrustRegistry()
    att = registry.attest("remote-llm", "verified", attested_by="volmarr",
                          note="DPA signed 2026-10-01")
    assert isinstance(att, TrustAttestation)
    assert registry.level_for(REMOTE) == "verified"
    assert registry.meets(REMOTE, "verified")
    assert registry.attestation_for("remote-llm").attested_by == "volmarr"


def test_attest_unknown_level_rejected():
    registry = BackendTrustRegistry()
    with pytest.raises(ValueError):
        registry.attest("remote-llm", "military-grade")


def test_attest_expiry_falls_back_to_default():
    registry = BackendTrustRegistry()
    registry.attest("remote-llm", "verified", expires_in_seconds=3600)
    assert registry.level_for(REMOTE) == "verified"
    # Simulate time passing: rewrite the attestation as expired.
    att = registry.attestation_for("remote-llm")
    object.__setattr__(att, "expires_at", time.time() - 1)
    assert att.expired
    assert registry.attestation_for("remote-llm") is None
    assert registry.level_for(REMOTE) == "basic"  # silent safe fallback


def test_attest_expiry_must_be_future():
    with pytest.raises(ValueError):
        TrustAttestation(level="verified", attested_at=100.0,
                         expires_at=50.0)


def test_revoke_drops_to_default():
    registry = BackendTrustRegistry()
    registry.attest("remote-llm", "verified")
    assert registry.revoke("remote-llm") is True
    assert registry.revoke("remote-llm") is False  # idempotent
    assert registry.level_for(REMOTE) == "basic"


def test_attestation_is_name_scoped():
    # Attesting "remote-llm" does not upgrade a different backend.
    registry = BackendTrustRegistry()
    registry.attest("remote-llm", "verified")
    other = FakeBackend("other-remote", remote=True)
    assert registry.level_for(other) == "basic"


def test_guard_uses_attested_trust():
    registry = BackendTrustRegistry()
    guard = PrivacyGuard(trust_registry=registry)
    strict_remote = DecisionPolicy(remote_inference=True,
                                   privacy_class="strict")
    # Unattested: blocked (slice 226 behavior preserved).
    assert guard.remote_allowed(REMOTE, strict_remote) is False
    # Attested to verified: allowed.
    registry.attest("remote-llm", "verified", attested_by="volmarr")
    assert guard.remote_allowed(REMOTE, strict_remote) is True
    guard.check_backend(REMOTE, strict_remote)  # no raise
    # Revoked: blocked again.
    registry.revoke("remote-llm")
    assert guard.remote_allowed(REMOTE, strict_remote) is False
    with pytest.raises(PrivacyViolation):
        guard.check_backend(REMOTE, strict_remote)


def test_guard_without_registry_keeps_defaults():
    guard = PrivacyGuard()
    assert guard.trust_registry is None
    assert guard._trust_level(REMOTE) == "basic"
    assert guard._trust_level(LOCAL) == "enclave"


def test_registry_round_trip():
    registry = BackendTrustRegistry()
    registry.attest("remote-llm", "verified", attested_by="v",
                    note="n")
    rebuilt = BackendTrustRegistry.from_dict(registry.to_dict())
    assert rebuilt.level_for(REMOTE) == "verified"
    assert rebuilt.attestation_for("remote-llm").note == "n"


def test_default_trust_helpers():
    assert default_trust_level(REMOTE) == "basic"
    assert default_trust_level(LOCAL) == "enclave"
    assert trust_rank("untrusted") == 0
    with pytest.raises(ValueError):
        trust_rank("nope")


def test_adversarial_self_attestation_downgrade():
    # A backend cannot attest *itself* to a higher level and have it
    # stick past operator review: revocation returns it to default.
    registry = BackendTrustRegistry()
    registry.attest("remote-llm", "enclave", attested_by="remote-llm")
    assert registry.level_for(REMOTE) == "enclave"
    registry.revoke("remote-llm")
    guard = PrivacyGuard(trust_registry=registry)
    policy = DecisionPolicy(remote_inference=True,
                            privacy_class="forbidden")
    # forbidden still never remote, even at enclave trust.
    assert guard.remote_allowed(REMOTE, policy) is False
