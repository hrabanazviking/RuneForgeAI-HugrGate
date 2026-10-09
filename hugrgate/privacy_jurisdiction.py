"""Jurisdiction metadata. Slice 230.

Data has a passport: where it is processed matters. This module
tracks which jurisdiction each backend operates in and enforces
operator-declared allowed jurisdictions at selection and attempt
time.

- :class:`JurisdictionRegistry` maps backend names to jurisdiction
  codes (``"local"``, ``"EU"``, ``"US"``, ...). Unlisted local
  backends default to ``"local"``; unlisted remote backends default
  to ``"unknown"`` — and ``"unknown"`` is never in an allowed set,
  so undeclared remotes are denied by default under a jurisdiction
  policy (fail closed).
- :class:`JurisdictionPolicy` holds the allowed set (``None`` = no
  restriction) and raises :class:`JurisdictionViolation` on breach.
- :class:`~hugrgate.privacy.PrivacyGuard` accepts
  ``jurisdiction_registry=`` and ``jurisdictions_allowed=`` and
  enforces them in ``remote_allowed`` / ``check_backend`` /
  ``filter_backends``.

Local backends are always jurisdiction-clean: data never crosses a
border when it never leaves the process.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import JurisdictionViolation
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "LOCAL_JURISDICTION",
    "UNKNOWN_JURISDICTION",
    "JurisdictionPolicy",
    "JurisdictionRegistry",
]

#: Jurisdiction code for in-process backends.
LOCAL_JURISDICTION = "local"
#: Jurisdiction code for remote backends with no declared jurisdiction.
#: Fail-closed: never matches an allowed set.
UNKNOWN_JURISDICTION = "unknown"


class JurisdictionRegistry:
    """Backend name -> jurisdiction code."""

    def __init__(self, jurisdictions: Mapping[str, str] | None = None):
        self._jurisdictions = {str(n): str(j)
                               for n, j in (jurisdictions or {}).items()}

    def declare(self, backend_name: str, jurisdiction: str) -> None:
        """Declare (or update) a backend's jurisdiction."""
        self._jurisdictions[str(backend_name)] = str(jurisdiction)
        logger.info("jurisdiction: backend %r declared in %r",
                    backend_name, jurisdiction)

    def jurisdiction_for(self, backend: Backend) -> str:
        """Jurisdiction code: declared, or ``local``/``unknown`` default."""
        declared = self._jurisdictions.get(backend.name)
        if declared is not None:
            return declared
        return LOCAL_JURISDICTION if not backend.is_remote \
            else UNKNOWN_JURISDICTION

    def to_dict(self) -> dict[str, str]:
        return dict(self._jurisdictions)

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> JurisdictionRegistry:
        return cls(jurisdictions=data)


class JurisdictionPolicy:
    """Allowed jurisdictions for remote data flows.

    Parameters
    ----------
    allowed:
        Set of jurisdiction codes data may flow to, or None for no
        restriction. ``"local"`` need not be listed: in-process flows
        are always permitted.
    registry:
        Optional :class:`JurisdictionRegistry` resolving backend names.
    """

    def __init__(self,
                 allowed: set[str] | frozenset[str] | None = None,
                 registry: JurisdictionRegistry | None = None):
        self.allowed = frozenset(allowed) if allowed is not None else None
        self.registry = registry or JurisdictionRegistry()

    def check(self, backend: Backend) -> str:
        """Return the jurisdiction, or raise :class:`JurisdictionViolation`.

        Local backends always pass. Remote backends pass only when no
        restriction is set or their jurisdiction is in the allowed set.
        """
        jurisdiction = self.registry.jurisdiction_for(backend)
        if not backend.is_remote:
            return jurisdiction
        if self.allowed is not None and jurisdiction not in self.allowed:
            raise JurisdictionViolation(
                f"backend {backend.name!r} operates in jurisdiction "
                f"{jurisdiction!r}, which is not in the allowed set "
                f"{sorted(self.allowed)}",
                backend=backend.name,
                jurisdiction=jurisdiction,
                allowed=sorted(self.allowed))
        return jurisdiction

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": sorted(self.allowed) if self.allowed is not None
            else None,
            "registry": self.registry.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JurisdictionPolicy:
        return cls(allowed=data.get("allowed"),
                   registry=JurisdictionRegistry.from_dict(
                       data.get("registry", {})))
