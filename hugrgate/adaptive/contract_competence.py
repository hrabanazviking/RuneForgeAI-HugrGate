"""Per-contract competence. Slice 139.

Domains (slice 138) are coarse: "numeric" covers everything from
thermostat readings to derivatives pricing. *Contracts* are finer — the
application's declared agreement about a decision: ``spec.metadata``
may carry ``"contract"`` (e.g. ``"fraud-score/v3"``) and ``"version"``.
:class:`PerContractCompetence` tracks ``(backend, contract)`` profiles so
the router learns that backend B is superb at ``fraud-score/v3`` while
mediocre at ``fraud-score/v4`` — a distinction a domain average would
erase.

Contract resolution for an event:

1. ``spec.metadata["contract"]`` when present (plus ``"/v" + version``
   when ``metadata["version"]`` is present);
2. otherwise the spec ``type`` — degrading gracefully to slice-138
   behavior rather than inventing a contract.

Like domains, contracts fall back: exact ``(backend, contract)`` →
backend global → ``None``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from hugrgate.adaptive.competence import (
    BackendCompetenceProfiles,
    CompetenceProfile,
)
from hugrgate.adaptive.telemetry import RouteEvent
from hugrgate.errors import SpecError
from hugrgate.spec import DecisionSpec

__all__ = [
    "PerContractCompetence",
    "contract_of_event",
    "contract_of_spec",
]


def contract_of_spec(spec: DecisionSpec) -> str:
    """Resolve the contract id for a spec."""
    metadata = spec.metadata or {}
    contract = metadata.get("contract")
    if isinstance(contract, str) and contract.strip():
        contract = contract.strip()
        version = metadata.get("version")
        if isinstance(version, str) and version.strip():
            return f"{contract}/v{version.strip()}"
        return contract
    if isinstance(spec.type, str) and spec.type:
        return spec.type
    return "unknown"


def contract_of_event(event: RouteEvent) -> str:
    spec = event.spec or {}
    metadata = spec.get("metadata") or {}
    contract = metadata.get("contract")
    if isinstance(contract, str) and contract.strip():
        contract = contract.strip()
        version = metadata.get("version")
        if isinstance(version, str) and version.strip():
            return f"{contract}/v{version.strip()}"
        return contract
    spec_type = spec.get("type")
    if isinstance(spec_type, str) and spec_type:
        return spec_type
    return "unknown"


class PerContractCompetence:
    """``(backend, contract)`` competence profiles with fallback."""

    def __init__(self, *, success_threshold: float = 0.7) -> None:
        self._global = BackendCompetenceProfiles(
            success_threshold=success_threshold)
        self._contracts: dict[tuple[str, str], CompetenceProfile] = {}
        self.success_threshold = self._global.success_threshold

    def _key(self, backend: str, contract: str) -> tuple[str, str]:
        if not backend or not contract:
            raise SpecError("backend and contract must be non-empty strings")
        return (backend, contract)

    def observe(self, backend: str, contract: str, *, quality: float,
                latency_ms: float = 0.0,
                cost: float = 0.0) -> CompetenceProfile:
        """Record one labeled outcome for ``(backend, contract)``."""
        if not isinstance(quality, (int, float)) or not 0.0 <= quality <= 1.0:
            raise SpecError(f"quality out of [0,1]: {quality!r}")
        if latency_ms < 0 or cost < 0:
            raise SpecError("latency_ms and cost must be >= 0")
        profile = self._contracts.get(self._key(backend, contract))
        if profile is None:
            profile = CompetenceProfile(backend=f"{backend}#{contract}")
            self._contracts[(backend, contract)] = profile
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
            self.observe(event.chosen, contract_of_event(event),
                         quality=quality, latency_ms=event.latency_ms,
                         cost=event.cost)
            used += 1
        return used

    def get(self, backend: str, contract: str) -> CompetenceProfile | None:
        profile = self._contracts.get((backend, contract))
        return CompetenceProfile.from_dict(profile.to_dict()) \
            if profile else None

    def get_with_fallback(self, backend: str,
                          contract: str) -> CompetenceProfile | None:
        """Exact contract profile → global backend profile → None."""
        exact = self.get(backend, contract)
        if exact is not None:
            return exact
        return self._global.get(backend)

    def contracts(self) -> list[str]:
        return sorted({contract for _, contract in self._contracts})

    def ranked_in_contract(self, contract: str) -> list[CompetenceProfile]:
        profiles = [CompetenceProfile.from_dict(p.to_dict())
                    for (backend, c), p in self._contracts.items()
                    if c == contract]
        profiles.sort(key=lambda p: (-p.wilson_lower, p.backend))
        return profiles

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "adaptive-contract-competence/v1",
            "success_threshold": self.success_threshold,
            "global": self._global.to_dict(),
            "contracts": {
                f"{backend}\x00{contract}": profile.to_dict()
                for (backend, contract), profile in self._contracts.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PerContractCompetence:
        if data.get("schema") != "adaptive-contract-competence/v1":
            raise SpecError(
                "unsupported contract-competence schema "
                f"{data.get('schema')!r}")
        obj = cls(success_threshold=float(
            data.get("success_threshold", 0.7)))
        obj._global = BackendCompetenceProfiles.from_dict(data["global"])
        for flat_key, payload in data.get("contracts", {}).items():
            backend, contract = flat_key.split("\x00")
            obj._contracts[(backend, contract)] = \
                CompetenceProfile.from_dict(payload)
        return obj
