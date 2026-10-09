"""Service authorization policy. Slice 419.

Threat T-12: the HTTP service exposes decide/configure endpoints
with no authentication or authorization. This module is the
deny-by-default policy engine that threat's mitigation names:

- :class:`AuthzPolicy` — roles map to capability sets; principals
  (API keys) map to roles. Everything not explicitly granted is
  denied: unknown principals, unknown capabilities, revoked keys.
- Credential checks use constant-time comparison, so a wrong key
  is indistinguishable (by timing) from an unknown key id.
- Keys are revocable and the store supports rotation (register
  the replacement, revoke the old) without touching role grants.

What this module is *not*: deployment wiring. TLS termination,
key distribution, and per-route enforcement in ``hugrgate/server``
remain operator responsibility (the threat model records this as
the residual for T-12). The :data:`ENDPOINT_CAPABILITIES` table
documents which capability each service operation requires so the
wiring is a lookup, not a judgment call.
"""

from __future__ import annotations

import hmac
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import AuthzDenied

__all__ = [
    "ENDPOINT_CAPABILITIES",
    "ROLES",
    "AuthzPolicy",
    "Principal",
]


#: Built-in roles. Applications may add their own via
#: :meth:`AuthzPolicy.define_role`; built-ins cannot be redefined.
ROLES: dict[str, frozenset[str]] = {
    # May call the decision endpoints; nothing else.
    "caller": frozenset({"decide"}),
    # May tune configuration (policy, backends) and read metrics.
    "operator": frozenset({"decide", "configure", "metrics"}),
    # May manage keys and roles; cannot decide (separation of duties:
    # the hand that mints keys never spends them).
    "admin": frozenset({"manage_keys", "metrics"}),
}

#: Which capability each service operation requires. The server
#: wiring calls ``policy.authorize(principal, capability)`` with
#: the capability named here.
ENDPOINT_CAPABILITIES: dict[str, str] = {
    "POST /decide": "decide",
    "POST /decide/batch": "decide",
    "POST /configure": "configure",
    "GET /metrics": "metrics",
    "POST /keys": "manage_keys",
    "DELETE /keys/{id}": "manage_keys",
}


@dataclass(frozen=True)
class Principal:
    """An authenticated caller: key id + resolved capability set."""
    key_id: str
    roles: tuple[str, ...]
    capabilities: frozenset[str] = field(compare=False)

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass
class _KeyRecord:
    secret: bytes
    roles: tuple[str, ...]
    revoked: bool = False


class AuthzPolicy:
    """Deny-by-default service authorization."""

    def __init__(self, roles: Mapping[str, frozenset[str]] | None = None) -> None:
        self._roles: dict[str, frozenset[str]] = dict(ROLES)
        if roles:
            for name, caps in roles.items():
                if name in self._roles:
                    raise ValueError(
                        f"cannot redefine built-in role {name!r}")
                self._roles[name] = frozenset(caps)
        self._keys: dict[str, _KeyRecord] = {}
        self._lock = threading.Lock()

    # -- roles -----------------------------------------------------
    def define_role(self, name: str,
                    capabilities: frozenset[str] | set[str]) -> None:
        if name in self._roles:
            raise ValueError(f"role {name!r} already defined")
        self._roles[name] = frozenset(capabilities)

    def role_capabilities(self, name: str) -> frozenset[str]:
        try:
            return self._roles[name]
        except KeyError:
            raise AuthzDenied(f"unknown role {name!r}",
                              reason="unknown_role") from None

    # -- keys ------------------------------------------------------
    def register_key(self, key_id: str, secret: bytes,
                     roles: tuple[str, ...] | list[str]) -> None:
        """Register (or rotate) an API key. Secrets need 32 bytes."""
        if not key_id:
            raise ValueError("key_id must be non-empty")
        if len(secret) < 32:
            raise ValueError("secret must be at least 32 bytes")
        role_tuple = tuple(roles)
        for role in role_tuple:
            if role not in self._roles:
                raise AuthzDenied(f"unknown role {role!r}",
                                  reason="unknown_role")
        if not role_tuple:
            raise ValueError("a key must carry at least one role")
        with self._lock:
            self._keys[key_id] = _KeyRecord(secret=bytes(secret),
                                            roles=role_tuple)

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key. Returns False when the id was unknown."""
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return False
            record.revoked = True
            return True

    def rotate_key(self, key_id: str) -> bytes:
        """Mint a fresh secret for ``key_id``, keeping its roles.

        The old secret stops working the moment this returns —
        atomic under the lock, so there is no window where both
        secrets are valid.
        """
        with self._lock:
            record = self._keys.get(key_id)
            if record is None or record.revoked:
                raise AuthzDenied(f"unknown or revoked key {key_id!r}",
                                  reason="unknown_key")
            new_secret = secrets.token_bytes(32)
            self._keys[key_id] = _KeyRecord(secret=new_secret,
                                            roles=record.roles)
            return new_secret

    # -- authentication / authorization -----------------------------
    def authenticate(self, key_id: str,
                     secret: bytes) -> Principal:
        """Verify a credential; return the principal or raise.

        Unknown key ids, revoked keys, and wrong secrets all raise
        the same :class:`AuthzDenied` — and the comparison is
        constant-time, so an attacker learns nothing from timing.
        """
        with self._lock:
            record = self._keys.get(key_id)
        # Compare against a dummy when unknown so the timing matches
        # the known-key path (no oracle for key-id enumeration).
        candidate = record.secret if record is not None else b"\x00" * 32
        ok = hmac.compare_digest(candidate, bytes(secret))
        if record is None or record.revoked or not ok:
            raise AuthzDenied("authentication failed",
                              reason="bad_credential")
        capabilities = frozenset().union(
            *(self._roles[r] for r in record.roles))
        return Principal(key_id=key_id, roles=record.roles,
                         capabilities=capabilities)

    def authorize(self, principal: Principal,
                  capability: str) -> Principal:
        """Grant check: deny-by-default. Returns the principal on grant."""
        if not principal.can(capability):
            raise AuthzDenied(
                f"principal {principal.key_id!r} lacks capability "
                f"{capability!r}", reason="forbidden",
                key_id=principal.key_id, capability=capability)
        return principal

    def check(self, key_id: str, secret: bytes,
              capability: str) -> Principal:
        """Authenticate + authorize in one call."""
        return self.authorize(self.authenticate(key_id, secret),
                              capability)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "roles": len(self._roles),
                "keys": len(self._keys),
                "revoked": sum(1 for r in self._keys.values()
                               if r.revoked),
            }
