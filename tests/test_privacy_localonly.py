"""Slice 231 — Local-only field enforcement.

Tests strip vs strict modes, nested local-only fields, input
non-mutation, guard integration, and adversarial cases (smuggled
nested secrets, strict-mode hard guarantee, error taxonomy).
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import (
    HugrGateError,
    LocalOnlyViolation,
    PrivacyViolation,
)
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_labels import FieldLabels, Sensitivity
from hugrgate.privacy_localonly import (
    LocalOnlyPolicy,
    LocalOnlyResult,
    enforce_local_only,
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
LABELS = FieldLabels({"api_key": "secret", "db.password": "secret"},
                      local_only={"api_key", "db"})


def test_local_backend_untouched():
    state = {"api_key": "k", "db": {"password": "p", "host": "h"}}
    result = enforce_local_only(state, LABELS, remote=False)
    assert result.clean and result.stripped == []
    assert result.state == state


def test_strip_mode_removes_local_only():
    state = {"api_key": "k", "db": {"password": "p", "host": "h"},
             "name": "n"}
    result = enforce_local_only(state, LABELS, remote=True)
    assert not result.clean
    # "db" is marked local-only: the whole subtree is covered.
    assert result.stripped == ["api_key", "db.host", "db.password"]
    assert result.state == {"name": "n"}


def test_local_only_leaf_keeps_siblings():
    labels = FieldLabels({"db.password": "secret"},
                         local_only={"db.password"})
    state = {"db": {"password": "p", "host": "h"}, "name": "n"}
    result = enforce_local_only(state, labels, remote=True)
    assert result.stripped == ["db.password"]
    assert result.state == {"db": {"host": "h"}, "name": "n"}


def test_strip_mode_prunes_emptied_parents():
    labels = FieldLabels({"db.password": "secret"}, local_only={"db"})
    state = {"db": {"password": "p"}, "name": "n"}
    result = enforce_local_only(state, labels, remote=True)
    assert result.state == {"name": "n"}  # emptied "db" pruned


def test_strict_mode_raises():
    policy = LocalOnlyPolicy(strict=True)
    state = {"api_key": "k", "name": "n"}
    with pytest.raises(LocalOnlyViolation) as exc:
        policy.enforce(state, LABELS, remote=True)
    assert exc.value.details["fields"] == ["api_key"]
    assert isinstance(exc.value, PrivacyViolation)


def test_strict_mode_clean_passes():
    policy = LocalOnlyPolicy(strict=True)
    result = policy.enforce({"name": "n"}, LABELS, remote=True)
    assert result.clean


def test_input_never_mutated():
    state = {"api_key": "k", "db": {"password": "p", "host": "h"}}
    snapshot = {"api_key": "k", "db": {"password": "p", "host": "h"}}
    enforce_local_only(state, LABELS, remote=True)
    assert state == snapshot


def test_enforce_for_backend():
    policy = LocalOnlyPolicy()
    state = {"api_key": "k"}
    assert policy.enforce_for_backend(state, LABELS, LOCAL).clean
    assert not policy.enforce_for_backend(state, LABELS, REMOTE).clean


def test_guard_integration():
    guard = PrivacyGuard()
    state = {"api_key": "k", "name": "n"}
    local_result = guard.enforce_local_only(state, LABELS, LOCAL)
    assert local_result.clean
    remote_result = guard.enforce_local_only(state, LABELS, REMOTE)
    assert remote_result.stripped == ["api_key"]
    with pytest.raises(LocalOnlyViolation):
        guard.enforce_local_only(state, LABELS, REMOTE, strict=True)


def test_no_local_only_labels_is_noop():
    labels = FieldLabels({"ssn": "secret"})  # not local-only
    result = enforce_local_only({"ssn": "1"}, labels, remote=True)
    assert result.clean and result.state == {"ssn": "1"}


def test_policy_to_dict():
    assert LocalOnlyPolicy(strict=True).to_dict() == {"strict": True}


def test_result_type():
    result = enforce_local_only({"a": 1}, LABELS, remote=True)
    assert isinstance(result, LocalOnlyResult)
    assert result.remote is True


def test_adversarial_deeply_nested_smuggle():
    # Attacker nests the local-only field three levels deep; the
    # parent-path marking ("db") still catches it.
    labels = FieldLabels(local_only={"db"})
    state = {"db": {"cluster": {"primary": {"password": "p"}}},
             "name": "n"}
    result = enforce_local_only(state, labels, remote=True)
    assert "db.cluster.primary.password" in result.stripped
    assert result.state == {"name": "n"}


def test_violation_taxonomy_and_wire():
    err = LocalOnlyViolation("leak", fields=["api_key"])
    assert err.code == "local_only_violation"
    assert err.recoverable is False
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert type(rebuilt) is LocalOnlyViolation
    assert rebuilt.details["fields"] == ["api_key"]


def test_sensitivity_levels_unaffected():
    # Local-only enforcement is orthogonal to sensitivity clearance:
    # a SECRET-but-not-local-only field passes through stripping.
    labels = FieldLabels({"ssn": Sensitivity.SECRET})
    result = enforce_local_only({"ssn": "1"}, labels, remote=True)
    assert result.clean
