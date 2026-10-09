"""Backend interface + registry. Slice 6."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

# Alias: BackendRegistry.list() shadows the builtin inside the class
# body, so annotations there cannot spell `list[...]` directly.
_StrList = list[str]
_BackendList = list["Backend"]

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
    def capabilities(self) -> dict[str, Any]:
        """What this backend can do: spec types, features, limits."""

    @abstractmethod
    def supports(self, spec: DecisionSpec) -> bool:
        """Can this backend handle this spec type?"""

    @abstractmethod
    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        """Make a decision. Must respect the spec's value space."""

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "backend": self.name}

    # Optional capabilities
    def warmup(self) -> None:  # noqa: B027 - intentional no-op hook
        pass

    def close(self) -> None:  # noqa: B027 - intentional no-op hook
        """Release resources held by this backend (slice 019).

        Default is a no-op. Backends holding model weights, file
        handles, or subprocesses override this; :meth:`HugrGate.close`
        calls it best-effort on every registered backend.
        """

    def batch(self, states: list[Mapping[str, Any]], spec: DecisionSpec,
              context: Mapping[str, Any] | None = None
              ) -> list[DecisionResult]:
        return [self.evaluate(s, spec, context) for s in states]

    def calibration_info(self) -> dict[str, Any]:
        return {"calibrated": False}

    def estimated_latency(self) -> float:
        return 100.0  # ms, conservative default

    def estimated_cost(self) -> float:
        return 0.0

    def privacy_properties(self) -> dict[str, Any]:
        return {"remote": self.is_remote, "data_retained": False}

    def hardware_requirements(self) -> dict[str, Any]:
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
        self._backends: dict[str, Backend] = {}
        self._lock = threading.RLock()

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
        with self._lock:
            if name in self._backends and not replace:
                raise SpecError(
                    f"backend {name!r} is already registered; "
                    f"pass replace=True to overwrite it")
            self._backends[name] = backend

    def unregister(self, name: str) -> bool:
        """Remove the backend called ``name``. Returns True if one was."""
        with self._lock:
            return self._backends.pop(name, None) is not None

    def get(self, name: str) -> Backend | None:
        with self._lock:
            return self._backends.get(name)

    def get_or_raise(self, name: str) -> Backend:
        """Return the backend called ``name`` or raise BackendUnavailable."""
        with self._lock:
            backend = self._backends.get(name)
        if backend is None:
            raise BackendUnavailable(f"unknown backend: {name}")
        return backend

    def list(self) -> _StrList:
        with self._lock:
            return list(self._backends.keys())

    def supporting(self, spec: DecisionSpec) -> _BackendList:
        with self._lock:
            return [b for b in self._backends.values() if b.supports(spec)]

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._backends

    def __len__(self) -> int:
        with self._lock:
            return len(self._backends)
