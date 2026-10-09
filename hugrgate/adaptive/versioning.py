"""Adaptive policy versioning. Slice 146.

Checkpoints (slice 145) are anonymous snapshots; *versions* are named,
lineaged releases. :class:`AdaptivePolicyVersioning` tracks the
lifecycle of adaptive routing policies:

- :meth:`create_version` mints ``v<n>`` with an optional parent,
  a human note, and a SHA-256 digest of the canonical policy state —
  so "which policy served request X?" (telemetry's ``policy_version``,
  slice 126) always resolves to exact bytes.
- :meth:`activate` flips the serving pointer; only one version is
  active at a time, and activation is recorded in history.
- :meth:`lineage` walks parent links back to the root, exposing the
  promotion chain for audit.
- :meth:`verify` recomputes a version's digest from a candidate state
  dict — the integrity check rollback (slice 145) and promotion flows
  use before trusting archived bytes.

Versions are immutable once created: there is no "edit v3", only "mint
v4 with v3 as parent". Mutable history is how incidents become
mysteries.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "AdaptivePolicyVersioning",
    "PolicyVersion",
    "digest_state",
]


def digest_state(state: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON of a policy state dict."""
    try:
        # Strict: no default=str — unserializable values must fail here,
        # not silently become their repr().
        canonical = json.dumps(dict(state), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise SpecError(
            f"policy state is not JSON-serializable: {exc}") from exc
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class PolicyVersion:
    """One immutable adaptive-policy release."""

    version_id: str
    parent_id: str | None
    created_at: float
    note: str
    state_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "note": self.note,
            "state_digest": self.state_digest,
        }


class AdaptivePolicyVersioning:
    """Named, lineaged, integrity-checked policy releases."""

    def __init__(self) -> None:
        self._versions: dict[str, PolicyVersion] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._active_id: str | None = None
        self._counter = 0
        self._history: list[dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self._versions)

    def __contains__(self, version_id: object) -> bool:
        return version_id in self._versions

    def create_version(self, state: Mapping[str, Any], *,
                       parent_id: str | None = None,
                       note: str = "") -> PolicyVersion:
        """Mint a new immutable version from a policy state dict."""
        if parent_id is not None and parent_id not in self._versions:
            raise SpecError(
                f"parent version {parent_id!r} does not exist")
        canonical = json.loads(json.dumps(dict(state), sort_keys=True))
        self._counter += 1
        version_id = f"v{self._counter}"
        version = PolicyVersion(
            version_id=version_id,
            parent_id=parent_id,
            created_at=time.time(),
            note=note,
            state_digest=digest_state(canonical),
        )
        self._versions[version_id] = version
        self._states[version_id] = canonical
        self._history.append({"action": "create", "version_id": version_id,
                              "parent_id": parent_id, "note": note,
                              "at": version.created_at})
        return version

    def activate(self, version_id: str) -> PolicyVersion:
        """Point the serving pointer at ``version_id``."""
        version = self._versions.get(version_id)
        if version is None:
            raise SpecError(f"unknown policy version {version_id!r}")
        previous = self._active_id
        self._active_id = version_id
        self._history.append({"action": "activate",
                              "version_id": version_id,
                              "previous": previous, "at": time.time()})
        return version

    @property
    def active(self) -> PolicyVersion | None:
        if self._active_id is None:
            return None
        return self._versions[self._active_id]

    def get(self, version_id: str) -> PolicyVersion | None:
        return self._versions.get(version_id)

    def state_for(self, version_id: str) -> dict[str, Any]:
        """The archived state bytes for a version (deep copy)."""
        state = self._states.get(version_id)
        if state is None:
            raise SpecError(f"unknown policy version {version_id!r}")
        return json.loads(json.dumps(state))

    def verify(self, version_id: str, state: Mapping[str, Any]) -> bool:
        """True iff ``state`` matches the version's recorded digest."""
        version = self._versions.get(version_id)
        if version is None:
            raise SpecError(f"unknown policy version {version_id!r}")
        return digest_state(state) == version.state_digest

    def lineage(self, version_id: str) -> list[PolicyVersion]:
        """Parent chain from ``version_id`` back to the root."""
        if version_id not in self._versions:
            raise SpecError(f"unknown policy version {version_id!r}")
        chain = []
        current: str | None = version_id
        seen = set()
        while current is not None:
            if current in seen:  # pragma: no cover - defensive
                raise SpecError(
                    f"version lineage cycle detected at {current!r}")
            seen.add(current)
            version = self._versions[current]
            chain.append(version)
            current = version.parent_id
        return chain

    def history(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._history]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "adaptive-policy-versions/v1",
            "active_id": self._active_id,
            "versions": {vid: v.to_dict()
                         for vid, v in self._versions.items()},
        }
