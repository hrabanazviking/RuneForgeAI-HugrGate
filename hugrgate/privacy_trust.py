"""Backend trust levels. Slice 229.

Not all backends deserve the same data. :class:`BackendTrustRegistry`
holds *attestations*: operator-signed claims that a backend meets a
trust level (``untrusted`` < ``basic`` < ``verified`` < ``enclave``).
Unattested backends fall back to :func:`default_trust_level`
(in-process = ``enclave``, remote = ``basic``). Attestations expire
and can be revoked; an expired or revoked attestation silently drops
back to the default — never to a higher level.

The registry plugs into :class:`~hugrgate.privacy.PrivacyGuard`
(``trust_registry=``), so the slice-226 class trust floors are
evaluated against attested trust rather than bare defaults.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "TRUST_ORDER",
    "BackendTrustRegistry",
    "TrustAttestation",
    "default_trust_level",
    "trust_rank",
]

#: Backend trust ladder, lowest to highest. Unattested backends use
#: :func:`default_trust_level`; slice 226 defined the ordering, slice
#: 229 adds the attested registry.
TRUST_ORDER = ("untrusted", "basic", "verified", "enclave")


def trust_rank(level: str) -> int:
    """Ordinal of a trust level (higher = more trusted)."""
    try:
        return TRUST_ORDER.index(level)
    except ValueError:
        raise ValueError(
            f"unknown trust level: {level!r}; expected one of "
            f"{list(TRUST_ORDER)}") from None


def default_trust_level(backend: Backend) -> str:
    """Trust level for a backend with no attestation.

    In-process backends run inside our trust boundary (``"enclave"``);
    remote backends are ``"basic"`` until attested otherwise.
    """
    return "enclave" if not backend.is_remote else "basic"


@dataclass
class TrustAttestation:
    """An operator's signed claim about a backend's trust level."""

    level: str
    attested_by: str = ""
    attested_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    note: str = ""

    def __post_init__(self):
        if self.level not in TRUST_ORDER:
            raise ValueError(
                f"unknown trust level: {self.level!r}; expected one of "
                f"{list(TRUST_ORDER)}")
        if self.expires_at is not None and \
                self.expires_at <= self.attested_at:
            raise ValueError("expires_at must be after attested_at")

    @property
    def expired(self) -> bool:
        """True when the attestation has passed its expiry."""
        return self.expires_at is not None and \
            time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "attested_by": self.attested_by,
            "attested_at": self.attested_at,
            "expires_at": self.expires_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrustAttestation:
        return cls(level=data["level"],
                   attested_by=data.get("attested_by", ""),
                   attested_at=data.get("attested_at", time.time()),
                   expires_at=data.get("expires_at"),
                   note=data.get("note", ""))


class BackendTrustRegistry:
    """Attested trust levels for named backends."""

    def __init__(self):
        self._attestations: dict[str, TrustAttestation] = {}

    def attest(self, backend_name: str, level: str, *,
               attested_by: str = "", expires_in_seconds: float | None = None,
               note: str = "") -> TrustAttestation:
        """Record (or replace) an attestation for a backend name."""
        now = time.time()
        attestation = TrustAttestation(
            level=level, attested_by=attested_by, attested_at=now,
            expires_at=(now + expires_in_seconds
                        if expires_in_seconds is not None else None),
            note=note)
        self._attestations[str(backend_name)] = attestation
        logger.info("trust: backend %r attested at %r by %r",
                    backend_name, level, attested_by or "operator")
        return attestation

    def revoke(self, backend_name: str) -> bool:
        """Drop an attestation; the backend falls back to its default."""
        if str(backend_name) in self._attestations:
            del self._attestations[str(backend_name)]
            logger.warning("trust: attestation revoked for backend %r",
                           backend_name)
            return True
        return False

    def attestation_for(self, backend_name: str) -> TrustAttestation | None:
        """The live attestation, or None when absent/expired."""
        attestation = self._attestations.get(str(backend_name))
        if attestation is not None and attestation.expired:
            return None
        return attestation

    def level_for(self, backend: Backend) -> str:
        """Effective trust level: live attestation or the default."""
        attestation = self.attestation_for(backend.name)
        if attestation is not None:
            return attestation.level
        return default_trust_level(backend)

    def rank_for(self, backend: Backend) -> int:
        """Numeric trust rank for comparisons."""
        return trust_rank(self.level_for(backend))

    def meets(self, backend: Backend, minimum: str) -> bool:
        """True when the backend's effective trust meets ``minimum``."""
        return self.rank_for(backend) >= trust_rank(minimum)

    def to_dict(self) -> dict[str, Any]:
        return {name: att.to_dict()
                for name, att in self._attestations.items()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BackendTrustRegistry:
        registry = cls()
        for name, att in data.items():
            registry._attestations[str(name)] = \
                TrustAttestation.from_dict(att)
        return registry

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._attestations)
