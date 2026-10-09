"""Per-domain competence. Slice 138.

A backend that shines at categorical classification may fumble numeric
regression. :class:`PerDomainCompetence` keeps one
:class:`~hugrgate.adaptive.competence.CompetenceProfile` per
``(backend, domain)`` pair, so the router can ask "how good is *this*
backend at *this kind* of work?" instead of averaging over everything.

Domain resolution order for an event:

1. ``spec.metadata["domain"]`` — the application knows best;
2. the spec ``type`` (``"categorical"``, ``"numeric"``, …) as fallback;
3. ``"unknown"`` — never crash routing for lack of a label.

:meth:`get_with_fallback` implements the graceful-degradation ladder:
exact ``(backend, domain)`` → backend's global profile → ``None``. The
router therefore always has *some* evidence, and cold domains inherit
the backend's overall reputation until they earn their own.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from hugrgate.errors import SpecError
from hugrgate.spec import DecisionSpec

from hugrgate.adaptive.competence import (
    BackendCompetenceProfiles,
    CompetenceProfile,
)
from hugrgate.adaptive.telemetry import RouteEvent

__all__ = [
    "UNKNOWN_DOMAIN",
    "domain_of_spec",
    "domain_of_event",
    "PerDomainCompetence",
]

UNKNOWN_DOMAIN = "unknown"


def domain_of_spec(spec: DecisionSpec) -> str:
    """Resolve the domain for a spec (metadata wins, type is fallback)."""
    metadata = spec.metadata or {}
    domain = metadata.get("domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip()
    if isinstance(spec.type, str) and spec.type:
        return spec.type
    return UNKNOWN_DOMAIN


def domain_of_event(event: RouteEvent) -> str:
    spec = event.spec or {}
    metadata = spec.get("metadata") or {}
    domain = metadata.get("domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip()
    spec_type = spec.get("type")
    if isinstance(spec_type, str) and spec_type:
        return spec_type
    return UNKNOWN_DOMAIN


class PerDomainCompetence:
    """``(backend, domain)`` competence profiles with fallback."""

    def __init__(self, *, success_threshold: float = 0.7) -> None:
        self._global = BackendCompetenceProfiles(
            success_threshold=success_threshold)
        self._domains: Dict[Tuple[str, str], CompetenceProfile] = {}
        self.success_threshold = self._global.success_threshold

    def _key(self, backend: str, domain: str) -> Tuple[str, str]:
        if not backend or not domain:
            raise SpecError("backend and domain must be non-empty strings")
        return (backend, domain)

    def observe(self, backend: str, domain: str, *, quality: float,
                latency_ms: float = 0.0,
                cost: float = 0.0) -> CompetenceProfile:
        """Record one labeled outcome for ``(backend, domain)``.

        Also folds into the backend's global profile — the domain view
        refines, never replaces, the overall picture.
        """
        if not isinstance(quality, (int, float)) or not 0.0 <= quality <= 1.0:
            raise SpecError(f"quality out of [0,1]: {quality!r}")
        if latency_ms < 0 or cost < 0:
            raise SpecError("latency_ms and cost must be >= 0")
        profile = self._domains.get(self._key(backend, domain))
        if profile is None:
            profile = CompetenceProfile(backend=f"{backend}@{domain}")
            self._domains[(backend, domain)] = profile
        profile.attempts += 1
        if quality >= self.success_threshold:
            profile.successes += 1
        profile.quality_sum += quality
        profile.latency_sum_ms += latency_ms
        profile.cost_sum += cost
        self._global.observe(backend, quality=quality,
                             latency_ms=latency_ms, cost=cost)
        return profile

    def update_from_telemetry(self,
                              events: Iterable[RouteEvent]) -> int:
        used = 0
        for event in events:
            if event.shadow or not event.labeled:
                continue
            quality = event.quality
            if quality is None:
                continue
            self.observe(event.chosen, domain_of_event(event),
                         quality=quality, latency_ms=event.latency_ms,
                         cost=event.cost)
            used += 1
        return used

    def get(self, backend: str, domain: str) -> Optional[CompetenceProfile]:
        profile = self._domains.get((backend, domain))
        return CompetenceProfile.from_dict(profile.to_dict()) \
            if profile else None

    def get_with_fallback(self, backend: str,
                          domain: str) -> Optional[CompetenceProfile]:
        """Exact domain profile → global backend profile → None."""
        exact = self.get(backend, domain)
        if exact is not None:
            return exact
        return self._global.get(backend)

    def domains(self) -> List[str]:
        return sorted({domain for _, domain in self._domains})

    def ranked_in_domain(self, domain: str) -> List[CompetenceProfile]:
        profiles = [CompetenceProfile.from_dict(p.to_dict())
                    for (backend, d), p in self._domains.items()
                    if d == domain]
        profiles.sort(key=lambda p: (-p.wilson_lower, p.backend))
        return profiles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "adaptive-domain-competence/v1",
            "success_threshold": self.success_threshold,
            "global": self._global.to_dict(),
            "domains": {
                f"{backend}\x00{domain}": profile.to_dict()
                for (backend, domain), profile in self._domains.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PerDomainCompetence":
        if data.get("schema") != "adaptive-domain-competence/v1":
            raise SpecError(
                "unsupported domain-competence schema "
                f"{data.get('schema')!r}")
        obj = cls(success_threshold=float(
            data.get("success_threshold", 0.7)))
        obj._global = BackendCompetenceProfiles.from_dict(data["global"])
        for flat_key, payload in data.get("domains", {}).items():
            backend, domain = flat_key.split("\x00")
            obj._domains[(backend, domain)] = \
                CompetenceProfile.from_dict(payload)
        return obj
