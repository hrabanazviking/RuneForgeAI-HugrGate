"""True-async backend evaluation for the decide path. Slice 282.

Slice 018 gave us :meth:`HugrGate.adecide`, but it unconditionally
pushed the *entire* decision — including natively async backends —
into a worker thread via :func:`asyncio.to_thread`.  This module is the
true async core path:

- :class:`AsyncBackend` — a runtime-checkable structural protocol: any
  backend with ``async def aevaluate(state, spec, context)`` speaks it,
  no inheritance required.
- :class:`AsyncBackendBase` — convenience base: subclasses
  :class:`Backend`, inherits the sync contract, and gets an
  ``aevaluate`` that delegates to :func:`asyncio.to_thread` by default
  (override it for genuinely non-blocking inference).
- :func:`evaluate_async` — the dispatch: awaits ``aevaluate`` when the
  backend speaks async, otherwise runs sync ``evaluate`` in a worker
  thread.  One call site, no guessing.

:class:`hugrgate.core.HugrGate.adecide` now routes through
:func:`evaluate_async`, so async backends stay on the event loop while
sync backends keep the old thread behavior — same contract, same
errors, same provenance either way.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from hugrgate.backend import Backend
from hugrgate.log import get_logger
from hugrgate.spec import DecisionSpec

logger = get_logger(__name__)

__all__ = [
    "AsyncBackend",
    "AsyncBackendBase",
    "evaluate_async",
    "is_async_backend",
]


@runtime_checkable
class AsyncBackend(Protocol):
    """Structural protocol for natively async backends.

    Only method members: ``runtime_checkable`` protocols support
    ``isinstance`` solely for methods, so ``name`` is deliberately not
    part of the protocol — :func:`is_async_backend` checks the
    ``aevaluate`` coroutine function only.
    """

    async def aevaluate(self, state: Mapping[str, Any],
                        spec: DecisionSpec,
                        context: Mapping[str, Any] | None = None
                        ) -> Any:
        """Evaluate asynchronously.  Same contract as
        :meth:`Backend.evaluate`, but a coroutine."""
        ...


class AsyncBackendBase(Backend):
    """Backend base class with a default async evaluation path.

    Subclass this (instead of :class:`Backend`) when the backend can
    evaluate without blocking the event loop: override ``aevaluate``
    with real non-blocking inference.  The default ``aevaluate``
    preserves the slice-018 behavior — sync ``evaluate`` in a worker
    thread — so existing backends gain async compatibility for free.
    """

    async def aevaluate(self, state: Mapping[str, Any],
                        spec: DecisionSpec,
                        context: Mapping[str, Any] | None = None) -> Any:
        """Default: run sync :meth:`evaluate` in a worker thread."""
        return await asyncio.to_thread(self.evaluate, state, spec, context)


def is_async_backend(backend: Any) -> bool:
    """True when ``backend`` speaks the async protocol natively.

    A coroutine attribute named ``aevaluate`` is the whole test —
    structural, so hand-rolled backends qualify without inheritance.
    """
    candidate = getattr(backend, "aevaluate", None)
    return callable(candidate) and asyncio.iscoroutinefunction(candidate)


async def evaluate_async(backend: Backend, state: Mapping[str, Any],
                         spec: DecisionSpec,
                         context: Mapping[str, Any] | None = None) -> Any:
    """Evaluate ``backend`` without blocking the event loop.

    Natively async backends are awaited in place; sync backends run in
    a worker thread (the slice-018 behavior).  Exceptions propagate
    unchanged — error translation stays the caller's job.
    """
    if is_async_backend(backend):
        logger.debug("backend %r evaluating on the event loop",
                     backend.name)
        return await backend.aevaluate(state, spec, context)
    logger.debug("backend %r evaluating in a worker thread", backend.name)
    return await asyncio.to_thread(backend.evaluate, state, spec, context)
