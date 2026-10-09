"""Backend competence profiles. Slice 137.

The bandit learns online; competence profiles remember *offline*. A
:class:`CompetenceProfile` is the long-run report card for one backend:
attempts, quality-weighted successes, mean latency, mean cost — plus a
**Wilson score lower bound** on the success rate, so ranking prefers
"10/10" over "1/1" and a battle-tested 85% over a lucky 100% on three
samples.

:class:`BackendCompetenceProfiles` is the registry:

- :meth:`observe` folds one labeled outcome in (online path);
- :meth:`update_from_telemetry` rebuilds from a telemetry store's
  labeled events (batch path, slice 126);
- :meth:`ranked` orders backends by Wilson lower bound — the
  exploitation-safe ordering;
- profiles serialize for versioning/rollback (slices 145–146).

"Success" is quality ≥ ``success_threshold``; quality itself is averaged
separately so near-misses still inform the mean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from hugrgate.errors import SpecError

from hugrgate.adaptive.telemetry import RouteEvent

__all__ = [
    "CompetenceProfile",
    "BackendCompetenceProfiles",
    "wilson_lower_bound",
]


def wilson_lower_bound(successes: int, trials: int,
                       z: float = 1.96) -> float:
    """Wilson score interval lower bound for a success proportion.

    ``z=1.96`` is the 95% interval. Zero trials → 0.0: no evidence is
    not evidence of competence.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise SpecError(
            f"invalid (successes={successes}, trials={trials})")
    if trials == 0:
        return 0.0
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = p + z * z / (2.0 * trials)
    spread = z * math.sqrt(p * (1.0 - p) / trials
                           + z * z / (4.0 * trials * trials))
    return max(0.0, (center - spread) / denom)


@dataclass
class CompetenceProfile:
    """Long-run report card for one backend."""

    backend: str
    attempts: int = 0
    successes: int = 0
    quality_sum: float = 0.0
    latency_sum_ms: float = 0.0
    cost_sum: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or not self.backend:
            raise SpecError("profile backend must be a non-empty string")
        for attr in ("attempts", "successes"):
            if getattr(self, attr) < 0:
                raise SpecError(f"{attr} must be >= 0")
        if self.successes > self.attempts:
            raise SpecError("successes cannot exceed attempts")

    @property
    def mean_quality(self) -> float:
        return self.quality_sum / self.attempts if self.attempts else 0.0

    @property
    def mean_latency_ms(self) -> float:
        return self.latency_sum_ms / self.attempts if self.attempts else 0.0

    @property
    def mean_cost(self) -> float:
        return self.cost_sum / self.attempts if self.attempts else 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def wilson_lower(self) -> float:
        """Conservative competence estimate: prefer proven over lucky."""
        return wilson_lower_bound(self.successes, self.attempts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "attempts": self.attempts,
            "successes": self.successes,
            "quality_sum": self.quality_sum,
            "latency_sum_ms": self.latency_sum_ms,
            "cost_sum": self.cost_sum,
            "mean_quality": self.mean_quality,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_cost": self.mean_cost,
            "success_rate": self.success_rate,
            "wilson_lower": self.wilson_lower,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompetenceProfile":
        return cls(
            backend=str(data["backend"]),
            attempts=int(data.get("attempts", 0)),
            successes=int(data.get("successes", 0)),
            quality_sum=float(data.get("quality_sum", 0.0)),
            latency_sum_ms=float(data.get("latency_sum_ms", 0.0)),
            cost_sum=float(data.get("cost_sum", 0.0)),
        )


class BackendCompetenceProfiles:
    """Registry of per-backend competence profiles."""

    def __init__(self, *, success_threshold: float = 0.7) -> None:
        if not 0.0 < success_threshold <= 1.0:
            raise SpecError(
                f"success_threshold must be in (0,1], got {success_threshold}")
        self.success_threshold = success_threshold
        self._profiles: Dict[str, CompetenceProfile] = {}

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, backend: object) -> bool:
        return backend in self._profiles

    def _get_or_create(self, backend: str) -> CompetenceProfile:
        profile = self._profiles.get(backend)
        if profile is None:
            profile = CompetenceProfile(backend=backend)
            self._profiles[backend] = profile
        return profile

    def observe(self, backend: str, *, quality: float,
                latency_ms: float = 0.0, cost: float = 0.0) -> CompetenceProfile:
        """Fold one labeled outcome into a backend's profile."""
        if not isinstance(backend, str) or not backend:
            raise SpecError("backend name must be a non-empty string")
        if not 0.0 <= quality <= 1.0:
            raise SpecError(f"quality out of [0,1]: {quality!r}")
        if latency_ms < 0 or cost < 0:
            raise SpecError("latency_ms and cost must be >= 0")
        profile = self._get_or_create(backend)
        profile.attempts += 1
        if quality >= self.success_threshold:
            profile.successes += 1
        profile.quality_sum += quality
        profile.latency_sum_ms += latency_ms
        profile.cost_sum += cost
        return profile

    def update_from_telemetry(self,
                              events: Iterable[RouteEvent]) -> int:
        """Rebuild observations from labeled, non-shadow telemetry."""
        used = 0
        for event in events:
            if event.shadow or not event.labeled:
                continue
            quality = event.quality
            if quality is None:
                continue
            self.observe(event.chosen, quality=quality,
                         latency_ms=event.latency_ms, cost=event.cost)
            used += 1
        return used

    def get(self, backend: str) -> Optional[CompetenceProfile]:
        profile = self._profiles.get(backend)
        if profile is None:
            return None
        # Defensive copy: profiles are registry-owned.
        return CompetenceProfile.from_dict(profile.to_dict())

    def ranked(self) -> List[CompetenceProfile]:
        """Backends best-first by Wilson lower bound (ties by name)."""
        profiles = [CompetenceProfile.from_dict(p.to_dict())
                    for p in self._profiles.values()]
        profiles.sort(key=lambda p: (-p.wilson_lower, p.backend))
        return profiles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "adaptive-competence/v1",
            "success_threshold": self.success_threshold,
            "profiles": {name: p.to_dict()
                         for name, p in self._profiles.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackendCompetenceProfiles":
        if data.get("schema") != "adaptive-competence/v1":
            raise SpecError(
                f"unsupported competence schema {data.get('schema')!r}")
        registry = cls(
            success_threshold=float(data.get("success_threshold", 0.7)))
        for name, payload in data.get("profiles", {}).items():
            registry._profiles[name] = CompetenceProfile.from_dict(payload)
        return registry
