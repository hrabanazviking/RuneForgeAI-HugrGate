"""Node capability advertisement. Slice 203.

Before a cluster can route work, every node must be able to say what it
*is*: which backends it serves, which spec types those cover, what it
costs, and what hardware stands behind it. :class:`NodeCapabilities`
is that self-description — built from the live
:class:`BackendRegistry` (never hand-written, so it cannot drift from
reality) and exchanged during discovery (slices 204-206) and routing
(slice 212).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.backend import BackendRegistry
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.protocol import PROTOCOL_VERSION
from hugrgate.errors import SpecError
from hugrgate.spec import DecisionSpec

__all__ = [
    "NodeCapabilities",
]


@dataclass
class NodeCapabilities:
    """A node's advertised service surface.

    Construct via :meth:`from_registry` / :meth:`from_gate` so the
    advertisement always reflects the actually-registered backends.
    """

    node_id: str
    display_name: str = ""
    backends: list[dict[str, Any]] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    hardware: dict[str, Any] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    hugrgate_version: str = HUGRGATE_VERSION
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id:
            raise SpecError("capabilities need a non-empty node_id")
        for entry in self.backends:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise SpecError(
                    "every advertised backend needs a dict with a 'name'")
        for entry in self.models:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise SpecError(
                    "every advertised model needs a dict with a 'name'")

    @classmethod
    def from_registry(cls, registry: BackendRegistry,
                      identity: NodeIdentity,
                      models: list[dict[str, Any]] | None = None,
                      features: list[str] | None = None) -> NodeCapabilities:
        """Build an advertisement from the live backend registry.

        Backend capability dicts come straight from
        :meth:`Backend.capabilities` — the same source ``/backends``
        serves — extended with the serving facts routing needs
        (latency/cost estimates, determinism, remote flag).
        """
        backends = []
        for name in sorted(registry.list()):
            backend = registry.get(name)
            if backend is None:  # defensive: list/get disagree
                continue
            caps = dict(backend.capabilities())
            caps["name"] = backend.name
            caps["is_remote"] = backend.is_remote
            caps["estimated_latency_ms"] = backend.estimated_latency()
            caps["estimated_cost"] = backend.estimated_cost()
            backends.append(caps)
        return cls(
            node_id=identity.node_id,
            display_name=identity.display_name,
            backends=backends,
            models=[dict(m) for m in (models or [])],
            hardware=_hardware_info(),
            features=list(features or []),
        )

    @classmethod
    def from_gate(cls, gate: Any, identity: NodeIdentity,
                  **kwargs: Any) -> NodeCapabilities:
        """Build from a :class:`HugrGate` (uses its registry)."""
        return cls.from_registry(gate.registry, identity, **kwargs)

    def backend_names(self) -> list[str]:
        return [b["name"] for b in self.backends]

    def spec_types(self) -> list[str]:
        """Union of spec types servable by this node, sorted."""
        types: set[str] = set()
        for backend in self.backends:
            for spec_type in backend.get("spec_types", []):
                types.add(spec_type)
        return sorted(types)

    def matches(self, spec: DecisionSpec) -> bool:
        """True when at least one advertised backend covers the spec type."""
        return spec.type in self.spec_types()

    def supports_backend(self, name: str) -> bool:
        return name in self.backend_names()

    def describe(self) -> str:
        return (f"node {self.node_id[:12]}… ({self.display_name or 'unnamed'}): "
                f"{len(self.backends)} backend(s) "
                f"[{', '.join(self.backend_names())}], spec types "
                f"[{', '.join(self.spec_types())}]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "backends": [dict(b) for b in self.backends],
            "models": [dict(m) for m in self.models],
            "hardware": dict(self.hardware),
            "features": list(self.features),
            "hugrgate_version": self.hugrgate_version,
            "protocol_version": self.protocol_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeCapabilities:
        if not isinstance(data, dict):
            raise SpecError(
                f"capabilities must be a dict, got {type(data).__name__}")
        version = data.get("protocol_version", PROTOCOL_VERSION)
        if version != PROTOCOL_VERSION:
            raise SpecError(
                f"capabilities protocol version {version} != "
                f"{PROTOCOL_VERSION}")
        try:
            return cls(
                node_id=data["node_id"],
                display_name=data.get("display_name", ""),
                backends=[dict(b) for b in data.get("backends", [])],
                models=[dict(m) for m in data.get("models", [])],
                hardware=dict(data.get("hardware", {})),
                features=list(data.get("features", [])),
                hugrgate_version=data.get("hugrgate_version",
                                          HUGRGATE_VERSION),
            )
        except KeyError as e:
            raise SpecError(
                f"capabilities missing required key: {e}") from e


def _hardware_info() -> dict[str, Any]:
    """Best-effort host facts; never raises (advertisement must not fail
    because the OS would not answer a question)."""
    info: dict[str, Any] = {}
    try:
        cpus = os.cpu_count()
    except NotImplementedError:
        cpus = None
    info["cpu_count"] = cpus
    return info
