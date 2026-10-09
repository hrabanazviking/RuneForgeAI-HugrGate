"""Shared deterministic fake backends for ensemble tests (slices 101-125).

These are test-only doubles: scripted, deterministic, no I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import Abstention, BackendError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "BIN_SPEC",
    "CAT_SPEC",
    "AbstainingBackend",
    "ConstantBackend",
    "FailingBackend",
    "FnBackend",
    "ScriptedBackend",
    "make_result",
]


def CAT_SPEC() -> DecisionSpec:
    return DecisionSpec(type="categorical",
                        options=["alpha", "beta", "gamma"])


def BIN_SPEC() -> DecisionSpec:
    return DecisionSpec(type="binary", statement="it happens")


def make_result(value: Any, distribution: dict[str, float],
                name: str = "fake") -> DecisionResult:
    """Build a consistent DecisionResult (probability = winner mass)."""
    peak = max(distribution.values())
    winners = [k for k, p in distribution.items() if p == peak]
    assert value in winners, "test helper: value must be a distribution peak"
    return DecisionResult(
        value=value,
        probability=distribution[value],
        distribution=dict(distribution),
        backend=name,
        model="fake",
    )


class ConstantBackend(Backend):
    """Always votes the same value with the same distribution."""

    def __init__(self, name: str, value: str,
                 distribution: dict[str, float],
                 spec_types: tuple = ("categorical", "binary", "ordinal")):
        self.name = name
        self._value = value
        self._distribution = dict(distribution)
        self._spec_types = spec_types
        self.calls = 0

    def capabilities(self) -> dict[str, Any]:
        return {"fake": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in self._spec_types

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        self.calls += 1
        return make_result(self._value, self._distribution, self.name)


class ScriptedBackend(Backend):
    """Returns canned results in order, then repeats the last."""

    def __init__(self, name: str, results: list[DecisionResult]):
        self.name = name
        self._results = list(results)
        self.calls = 0

    def capabilities(self) -> dict[str, Any]:
        return {"fake": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        self.calls += 1
        idx = min(self.calls - 1, len(self._results) - 1)
        return self._results[idx]


class FailingBackend(Backend):
    """Always raises BackendError."""

    def __init__(self, name: str, message: str = "boom"):
        self.name = name
        self._message = message

    def capabilities(self) -> dict[str, Any]:
        return {"fake": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        raise BackendError(self._message)


class AbstainingBackend(Backend):
    """Always raises Abstention."""

    def __init__(self, name: str):
        self.name = name

    def capabilities(self) -> dict[str, Any]:
        return {"fake": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        raise Abstention("test abstention")


class FnBackend(Backend):
    """Decides via a callable: fn(state, spec) -> DecisionResult."""

    def __init__(self, name: str,
                 fn: Callable[[Mapping[str, Any], DecisionSpec],
                             DecisionResult]):
        self.name = name
        self._fn = fn

    def capabilities(self) -> dict[str, Any]:
        return {"fake": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        return self._fn(state, spec)
