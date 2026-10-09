"""Hostile backend doubles for the backend gauntlet (slice 490).

Real backends fail in boring ways; hostile ones fail in *adversarial*
ways: raising outside ``Exception``, returning garbage instead of a
``DecisionResult``, or contradicting the spec. The gate's contract
is total containment — ``HugrGate.decide`` must only ever let
taxonomy errors escape — and these doubles prove it.

Each double is a real :class:`hugrgate.backend.Backend`; the tests
drive them through the live ``HugrGate.decide`` path.
"""

from __future__ import annotations

from typing import Any

from hugrgate.backend import Backend
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "BadDistributionBackend",
    "BaseExceptionBackend",
    "ExplodingBackend",
    "HostileBackend",
    "KeyboardInterruptBackend",
    "NaNBackend",
    "NoneBackend",
    "OutOfSpaceBackend",
    "SystemExitBackend",
    "WrongTypeBackend",
]


class HostileBackend(Backend):
    """Base for hostile doubles: deterministic, categorical-only."""

    name = "hostile"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        raise NotImplementedError


class ExplodingBackend(HostileBackend):
    """Raises a plain RuntimeError from evaluate()."""

    name = "exploding"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        raise RuntimeError("backend blew up")


class BaseExceptionBackend(HostileBackend):
    """Raises raw BaseException — outside ``except Exception``."""

    name = "base-exception"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        raise BaseException("hostile base exception")


class KeyboardInterruptBackend(HostileBackend):
    """A hostile backend that tries to kill the host's control flow."""

    name = "keyboard-interrupt"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        raise KeyboardInterrupt()


class SystemExitBackend(HostileBackend):
    """A hostile backend that tries to exit the host process."""

    name = "system-exit"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        raise SystemExit(3)


class NaNBackend(HostileBackend):
    """Returns a NaN probability (rejected by DecisionResult itself)."""

    name = "nan"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        return DecisionResult(value="a", probability=float("nan"),
                              distribution={"a": 1.0, "b": 0.0})


class WrongTypeBackend(HostileBackend):
    """Returns a string instead of a DecisionResult."""

    name = "wrong-type"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> Any:
        return "not a result"


class NoneBackend(HostileBackend):
    """Returns None instead of a DecisionResult."""

    name = "none"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> Any:
        return None


class OutOfSpaceBackend(HostileBackend):
    """Returns a value outside the spec's decision space."""

    name = "out-of-space"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        return DecisionResult(value="zzz", probability=0.9,
                              distribution={"zzz": 0.9, "a": 0.1})


class BadDistributionBackend(HostileBackend):
    """Returns a distribution that does not sum to 1."""

    name = "bad-distribution"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.9})
