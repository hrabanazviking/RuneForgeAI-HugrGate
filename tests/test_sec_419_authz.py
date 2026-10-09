"""Slice 419 — service authorization policy.

Negative tests: unknown keys, wrong secrets, revoked keys, role
escalation, unknown capabilities, and built-in-role redefinition
must all be denied.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import AuthzDenied
from hugrgate.security.authz import (
    ENDPOINT_CAPABILITIES,
    ROLES,
    AuthzPolicy,
)


def _policy() -> AuthzPolicy:
    policy = AuthzPolicy()
    policy.register_key("caller-1", b"c" * 32, ("caller",))
    policy.register_key("op-1", b"o" * 32, ("operator",))
    policy.register_key("admin-1", b"a" * 32, ("admin",))
    return policy


def test_caller_can_decide():
    p = _policy().check("caller-1", b"c" * 32, "decide")
    assert p.key_id == "caller-1"
    assert p.can("decide")


def test_unknown_key_denied():
    with pytest.raises(AuthzDenied, match="authentication failed"):
        _policy().authenticate("ghost", b"x" * 32)


def test_wrong_secret_denied():
    with pytest.raises(AuthzDenied):
        _policy().authenticate("caller-1", b"z" * 32)


def test_short_secret_denied():
    with pytest.raises(AuthzDenied):
        _policy().authenticate("caller-1", b"short")


def test_revoked_key_denied():
    policy = _policy()
    assert policy.revoke_key("caller-1") is True
    with pytest.raises(AuthzDenied):
        policy.authenticate("caller-1", b"c" * 32)


def test_revoke_unknown_returns_false():
    assert _policy().revoke_key("nobody") is False


def test_role_escalation_denied():
    # A caller must not reach operator capabilities; an admin must
    # not decide (separation of duties).
    policy = _policy()
    caller = policy.authenticate("caller-1", b"c" * 32)
    with pytest.raises(AuthzDenied, match="lacks capability"):
        policy.authorize(caller, "configure")
    admin = policy.authenticate("admin-1", b"a" * 32)
    with pytest.raises(AuthzDenied, match="lacks capability"):
        policy.authorize(admin, "decide")


def test_operator_grants():
    policy = _policy()
    op = policy.authenticate("op-1", b"o" * 32)
    for cap in ("decide", "configure", "metrics"):
        assert policy.authorize(op, cap).key_id == "op-1"
    with pytest.raises(AuthzDenied):
        policy.authorize(op, "manage_keys")


def test_unknown_capability_denied():
    policy = _policy()
    caller = policy.authenticate("caller-1", b"c" * 32)
    with pytest.raises(AuthzDenied):
        policy.authorize(caller, "launch_missiles")


def test_unknown_role_rejected_at_registration():
    policy = AuthzPolicy()
    with pytest.raises(AuthzDenied, match="unknown role"):
        policy.register_key("k", b"k" * 32, ("emperor",))


def test_builtin_role_cannot_be_redefined():
    policy = AuthzPolicy()
    with pytest.raises(ValueError, match="built-in role"):
        AuthzPolicy(roles={"caller": frozenset({"everything"})})
    with pytest.raises(ValueError, match="already defined"):
        policy.define_role("operator", frozenset({"x"}))


def test_custom_role():
    policy = _policy()
    policy.define_role("reader", frozenset({"metrics"}))
    policy.register_key("r-1", b"r" * 32, ("reader",))
    principal = policy.check("r-1", b"r" * 32, "metrics")
    assert principal.roles == ("reader",)
    with pytest.raises(AuthzDenied):
        policy.authorize(principal, "decide")


def test_rotation_kills_old_secret():
    policy = _policy()
    new_secret = policy.rotate_key("caller-1")
    assert len(new_secret) == 32
    with pytest.raises(AuthzDenied):
        policy.authenticate("caller-1", b"c" * 32)  # old secret dead
    assert policy.check("caller-1", new_secret, "decide").key_id == "caller-1"


def test_rotate_unknown_key_denied():
    with pytest.raises(AuthzDenied):
        _policy().rotate_key("ghost")


def test_weak_secret_rejected_at_registration():
    policy = AuthzPolicy()
    with pytest.raises(ValueError, match="32 bytes"):
        policy.register_key("k", b"tiny", ("caller",))
    with pytest.raises(ValueError, match="at least one role"):
        policy.register_key("k", b"k" * 32, ())


def test_endpoint_table_covers_roles():
    # Every capability granted to a built-in role must be required
    # by at least one documented endpoint — no dead grants.
    granted = set().union(*ROLES.values())
    required = set(ENDPOINT_CAPABILITIES.values())
    assert granted <= required, granted - required


def test_stats():
    policy = _policy()
    policy.revoke_key("op-1")
    stats = policy.stats()
    assert stats["keys"] == 3
    assert stats["revoked"] == 1
    assert stats["roles"] >= len(ROLES)


def test_error_code_and_recoverability():
    err = AuthzDenied("no")
    assert err.code == "authz_denied"
    assert err.recoverable is False
