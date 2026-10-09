"""Backend interface + registry. Slice 6."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional

from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "Backend",
    "BackendRegistry",
]


class Backend(ABC):
    """A replaceable intelligence implementation.

    The application depends on the decision contract, not the provider.
    """

    name: str = "unnamed"
    is_remote: bool = False

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """What this backend can do: spec types, features, limits."""

    @abstractmethod
    def supports(self, spec: DecisionSpec) -> bool:
        """Can this backend handle this spec type?"""

    @abstractmethod
    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        """Make a decision. Must respect the spec's value space."""

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "backend": self.name}

    # Optional capabilities
    def warmup(self) -> None:
        pass

    def batch(self, states: List[Mapping[str, Any]], spec: DecisionSpec,
              context: Optional[Mapping[str, Any]] = None
              ) -> List[DecisionResult]:
        return [self.evaluate(s, spec, context) for s in states]

    def calibration_info(self) -> Dict[str, Any]:
        return {"calibrated": False}

    def estimated_latency(self) -> float:
        return 100.0  # ms, conservative default

    def estimated_cost(self) -> float:
        return 0.0

    def privacy_properties(self) -> Dict[str, Any]:
        return {"remote": self.is_remote, "data_retained": False}

    def hardware_requirements(self) -> Dict[str, Any]:
        return {}


class BackendRegistry:
    """Registry of available backends."""

    def __init__(self):
        self._backends: Dict[str, Backend] = {}

    def register(self, backend: Backend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> Optional[Backend]:
        return self._backends.get(name)

    def list(self) -> List[str]:
        return list(self._backends.keys())

    def supporting(self, spec: DecisionSpec) -> List[Backend]:
        return [b for b in self._backends.values() if b.supports(spec)]
