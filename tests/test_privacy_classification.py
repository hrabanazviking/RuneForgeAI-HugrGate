"""Slice 226 — Privacy classification v2.

The old binary standard/strict classes become a five-rung ordered
ladder (public < standard < sensitive < strict < forbidden) with
machine-enforceable semantics: minimum backend trust, cache
retention, remote eligibility, and provenance mode. Tests cover the
ladder itself, policy acceptance, guard enforcement at selection and
attempt time, and adversarial cases (typos, forbidden-class exfil
attempts, unverified remotes carrying strict data).
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import PolicyError, PrivacyViolation
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import (
    CLASS_SEMANTICS,
    NON_CACHEABLE_PRIVACY_CLASSES,
    PRIVACY_CLASS_ORDER,
    TRUST_ORDER,
    PrivacyGuard,
    at_least,
    class_rank,
    default_trust_level,
    provenance_mode_for,
    semantics_for,
    trust_rank,
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


LOCAL = FakeBackend("local")
REMOTE = FakeBackend("remote", remote=True)


# -- ladder structure --------------------------------------------------------

def test_class_order_is_total_and_documented():
    assert PRIVACY_CLASS_ORDER == ("public", "standard", "sensitive",
                                  "strict", "forbidden")
    assert [class_rank(c) for c in PRIVACY_CLASS_ORDER] == [0, 1, 2, 3, 4]


def test_policy_accepts_all_five_classes():
    for cls in PRIVACY_CLASS_ORDER:
        assert DecisionPolicy(privacy_class=cls).privacy_class == cls


def test_policy_classes_match_privacy_ladder():
    assert set(DecisionPolicy.PRIVACY_CLASSES) == set(PRIVACY_CLASS_ORDER)
    assert set(CLASS_SEMANTICS) == set(PRIVACY_CLASS_ORDER)


def test_semantics_have_required_keys():
    for cls, sem in CLASS_SEMANTICS.items():
        assert set(sem) == {"min_trust", "cacheable", "remote_eligible",
                            "provenance"}, cls
        assert sem["min_trust"] in TRUST_ORDER
        assert sem["provenance"] in ("full", "keys", "redacted", "none")


def test_at_least_ordering():
    assert at_least("forbidden", "strict")
    assert at_least("strict", "strict")
    assert not at_least("standard", "sensitive")
    assert at_least("public", "public")


def test_unknown_class_rejected_loudly():
    with pytest.raises(ValueError):
        class_rank("strcit")
    with pytest.raises(ValueError):
        semantics_for("topsecret")
    with pytest.raises(ValueError):
        provenance_mode_for("")


def test_policy_typo_rejected():
    # A misspelled "strict" must never silently degrade to "standard".
    with pytest.raises(PolicyError):
        DecisionPolicy(privacy_class="strcit")
    with pytest.raises(PolicyError):
        DecisionPolicy(privacy_class="Strict")


def test_semantics_are_copies():
    sem = semantics_for("strict")
    sem["cacheable"] = True
    assert semantics_for("strict")["cacheable"] is False


# -- trust defaults ----------------------------------------------------------

def test_default_trust_levels():
    assert default_trust_level(LOCAL) == "enclave"
    assert default_trust_level(REMOTE) == "basic"
    assert trust_rank("untrusted") < trust_rank("basic") < \
        trust_rank("verified") < trust_rank("enclave")
    with pytest.raises(ValueError):
        trust_rank("military-grade")


# -- guard enforcement --------------------------------------------------------

def test_standard_remote_still_allowed():
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True)  # standard
    assert guard.remote_allowed(REMOTE, policy) is True
    guard.check_backend(REMOTE, policy)  # no raise


def test_forbidden_class_blocks_remote_despite_permissive_policy():
    # Adversarial: operator flips policy.remote_inference=True and the
    # guard is in "allow" mode — forbidden-class data still never
    # leaves the process.
    guard = PrivacyGuard(remote_inference="allow")
    policy = DecisionPolicy(remote_inference=True,
                            privacy_class="forbidden")
    assert guard.remote_allowed(REMOTE, policy) is False
    with pytest.raises(PrivacyViolation) as exc:
        guard.check_backend(REMOTE, policy)
    assert "forbidden" in str(exc.value)


def test_forbidden_class_allows_local_backend():
    guard = PrivacyGuard()
    policy = DecisionPolicy(privacy_class="forbidden")
    assert guard.remote_allowed(LOCAL, policy) is True
    guard.check_backend(LOCAL, policy)  # no raise


def test_strict_requires_verified_remote():
    # Hardening (slice 226): an unattested remote backend may no longer
    # carry strict data even when the policy would allow remote.
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True, privacy_class="strict")
    assert guard.remote_allowed(REMOTE, policy) is False
    with pytest.raises(PrivacyViolation) as exc:
        guard.check_backend(REMOTE, policy)
    assert "verified" in str(exc.value)


def test_strict_allows_local_backend():
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True, privacy_class="strict")
    assert guard.remote_allowed(LOCAL, policy) is True
    guard.check_backend(LOCAL, policy)  # no raise


def test_sensitive_remote_allowed_at_basic_trust():
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True,
                            privacy_class="sensitive")
    assert guard.remote_allowed(REMOTE, policy) is True


def test_guard_forbidden_mode_still_wins():
    guard = PrivacyGuard(remote_inference="forbidden")
    policy = DecisionPolicy(remote_inference=True, privacy_class="public")
    assert guard.remote_allowed(REMOTE, policy) is False
    with pytest.raises(PrivacyViolation):
        guard.check_backend(REMOTE, policy)


def test_filter_backends_excludes_class_blocked():
    guard = PrivacyGuard()
    policy = DecisionPolicy(remote_inference=True,
                            privacy_class="forbidden")
    assert [b.name for b in guard.filter_backends([LOCAL, REMOTE], policy)] \
        == ["local"]


# -- cache + provenance semantics --------------------------------------------

def test_cache_allowed_follows_ladder():
    assert PrivacyGuard.cache_allowed(DecisionPolicy(privacy_class="public"))
    assert PrivacyGuard.cache_allowed(DecisionPolicy())
    assert PrivacyGuard.cache_allowed(
        DecisionPolicy(privacy_class="sensitive"))
    assert not PrivacyGuard.cache_allowed(
        DecisionPolicy(privacy_class="strict"))
    assert not PrivacyGuard.cache_allowed(
        DecisionPolicy(privacy_class="forbidden"))
    assert NON_CACHEABLE_PRIVACY_CLASSES == {"strict", "forbidden"}


def test_provenance_modes_follow_ladder():
    assert provenance_mode_for("public") == "full"
    assert provenance_mode_for("standard") == "keys"
    assert provenance_mode_for("sensitive") == "keys"
    assert provenance_mode_for("strict") == "redacted"
    assert provenance_mode_for("forbidden") == "none"
