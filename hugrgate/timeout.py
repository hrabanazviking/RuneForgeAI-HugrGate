"""Timeouts — per-decision deadline enforcement via threads. Slice 19.

The decision function runs on a daemon worker thread while the caller
joins with the deadline. On breach a :class:`TimeoutError` is raised;
the worker thread is daemonized so a hung backend can never block
process exit (it may still finish in the background — threads cannot be
killed, a documented limitation).

The deadline for a backend is::

    min(policy.maximum_latency_ms, backend.estimated_latency_ms * headroom)

when the policy sets a latency cap, else
``backend.estimated_latency_ms * headroom``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import TimeoutError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "TimeoutBackend",
    "deadline_ms_for",
    "evaluate_with_timeout",
    "run_with_deadline",
]


def run_with_deadline(fn: Callable[[], Any], deadline_s: float,
                      name: str = "task") -> Any:
    """Run ``fn``; raise :class:`TimeoutError` if it exceeds the deadline.

    ``deadline_s`` must be positive. Exceptions raised by ``fn`` itself
    propagate unchanged.
    """
    if deadline_s <= 0:
        raise ValueError("deadline_s must be positive")
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = fn()
        except BaseException as e:  # noqa: BLE001 - must ferry everything
            box["error"] = e

    worker = threading.Thread(target=target, name=f"hugrgate-{name}",
                              daemon=True)
    worker.start()
    worker.join(deadline_s)
    if worker.is_alive():
        raise TimeoutError(
            f"{name} exceeded deadline of {deadline_s * 1000:.1f}ms",
            deadline_ms=deadline_s * 1000)
    if "error" in box:
        raise box["error"]
    return box.get("result")


def deadline_ms_for(backend: Backend,
                    policy: DecisionPolicy | None = None,
                    headroom: float = 1.5) -> float:
    """Compute the per-decision deadline for a backend in milliseconds."""
    estimate = max(backend.estimated_latency(), 0.1) * headroom
    if policy is not None and policy.maximum_latency_ms is not None:
        return min(policy.maximum_latency_ms, estimate)
    return estimate


def evaluate_with_timeout(backend: Backend, state: Mapping[str, Any],
                          spec: DecisionSpec, deadline_ms: float,
                          context: Mapping[str, Any] | None = None
                          ) -> DecisionResult:
    """Evaluate a backend, raising :class:`TimeoutError` past the deadline."""
    return run_with_deadline(
        lambda: backend.evaluate(state, spec, context),
        deadline_ms / 1000.0,
        name=f"backend:{backend.name}")


class TimeoutBackend(Backend):
    """A :class:`Backend` wrapper that enforces a per-decision deadline.

    Wraps any backend; ``evaluate`` raises :class:`TimeoutError` when the
    inner backend exceeds
    ``min(policy.maximum_latency_ms, estimated_latency * headroom)``.
    The wrapper keeps the inner backend's name so results attribute
    correctly; ``metadata["timeout_guarded"]`` marks the enforcement.
    """

    def __init__(self, backend: Backend,
                 policy: DecisionPolicy | None = None,
                 headroom: float = 1.5,
                 explicit_deadline_ms: float | None = None):
        self.wrapped = backend
        self.name = backend.name
        self.is_remote = backend.is_remote
        self.policy = policy or DecisionPolicy()
        self.headroom = headroom
        self.explicit_deadline_ms = explicit_deadline_ms

    @property
    def deadline_ms(self) -> float:
        if self.explicit_deadline_ms is not None:
            return self.explicit_deadline_ms
        return deadline_ms_for(self.wrapped, self.policy, self.headroom)

    def capabilities(self) -> dict[str, Any]:
        caps = dict(self.wrapped.capabilities())
        caps["timeout_guarded"] = True
        caps["deadline_ms"] = self.deadline_ms
        return caps

    def supports(self, spec: DecisionSpec) -> bool:
        return self.wrapped.supports(spec)

    def estimated_latency(self) -> float:
        return self.deadline_ms

    def health(self) -> dict[str, Any]:
        h = dict(self.wrapped.health())
        h["timeout_guarded"] = True
        return h

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        result = evaluate_with_timeout(
            self.wrapped, state, spec, self.deadline_ms, context)
        result.metadata["timeout_guarded"] = True
        result.metadata["deadline_ms"] = self.deadline_ms
        return result
