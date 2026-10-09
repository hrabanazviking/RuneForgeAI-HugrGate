"""Backend interface + registry. Slice 6."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional

from hugrgate.errors import BackendUnavailable, SpecError
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
    """Registry of available backends.

    Invariants:
    - only :class:`Backend` instances with a non-empty string name
      may be registered;
    - names are unique: re-registering a name raises ``SpecError``
      unless ``replace=True``.
    """

    def __init__(self):
        self._backends: Dict[str, Backend] = {}

    def register(self, backend: Backend, *, replace: bool = False) -> None:
        """Add ``backend`` under its ``name``.

        Raises ``TypeError`` for non-``Backend`` objects, ``SpecError``
        for a missing/blank name or a duplicate name (without
        ``replace=True``).
        """
        if not isinstance(backend, Backend):
            raise TypeError(
                f"can only register Backend instances, got "
                f"{type(backend).__name__}")
        name = backend.name
        if not isinstance(name, str) or not name.strip():
            raise SpecError(
                f"backend name must be a non-empty string, got {name!r}")
        if name in self._backends and not replace:
            raise SpecError(
                f"backend {name!r} is already registered; "
                f"pass replace=True to overwrite it")
        self._backends[name] = backend

    def unregister(self, name: str) -> bool:
        """Remove the backend called ``name``. Returns True if one was."""
        return self._backends.pop(name, None) is not None

    def get(self, name: str) -> Optional[Backend]:
        return self._backends.get(name)

    def get_or_raise(self, name: str) -> Backend:
        """Return the backend called ``name`` or raise BackendUnavailable."""
        backend = self._backends.get(name)
        if backend is None:
            raise BackendUnavailable(f"unknown backend: {name}")
        return backend

    def list(self) -> List[str]:
        return list(self._backends.keys())

    def supporting(self, spec: DecisionSpec) -> List[Backend]:
        return [b for b in self._backends.values() if b.supports(spec)]

    def __contains__(self, name: object) -> bool:
        return name in self._backends

    def __len__(self) -> int:
        return len(self._backends)
