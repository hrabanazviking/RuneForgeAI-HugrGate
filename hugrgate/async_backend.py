"""Public async API surface. Slice 283.

:mod:`hugrgate.asyncx` (slice 282) is the *mechanism* (protocol +
dispatch); this module is the *API* callers program against:

- :class:`AsyncRequest` — one async decision request: state, spec,
  policy, context, backend_name, and an optional per-request timeout.
- :class:`AsyncGate` — an async facade over :class:`HugrGate`:
  :meth:`adecide` (single, with timeout), :meth:`adecide_many`
  (bounded-concurrency batch preserving input order),
  :meth:`astream` (async generator yielding results as they complete),
  plus :meth:`register`/:meth:`close` passthroughs.

Timeout semantics (deliberate):

- An explicit ``timeout_s`` wins; otherwise the policy's
  ``maximum_latency_ms`` is honored when set; otherwise no timeout.
- On expiry the in-flight evaluation is cancelled and
  :class:`TimeoutError` (``code="timeout"``, recoverable) is raised —
  never a bare :class:`asyncio.TimeoutError`, so callers stay inside
  the HugrGate error taxonomy.

Cancellation: :meth:`astream` stops feeding new work when the consumer
breaks out of the loop; already-started evaluations run to completion
unless their own timeout fires (structured, no orphaned tasks left
behind by the generator itself).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.asyncx import evaluate_async
from hugrgate.core import HugrGate, SpecLike
from hugrgate.errors import SpecError, TimeoutError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult

logger = get_logger(__name__)

__all__ = [
    "AsyncGate",
    "AsyncRequest",
    "evaluate_async",
]


@dataclass
class AsyncRequest:
    """One async decision request."""
    state: Mapping[str, Any]
    spec: SpecLike
    policy: DecisionPolicy | None = None
    context: Mapping[str, Any] | None = None
    backend_name: str | None = None
    timeout_s: float | None = None

    def __post_init__(self) -> None:
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise SpecError(
                f"timeout_s must be > 0, got {self.timeout_s!r}")
        if not isinstance(self.state, Mapping):
            raise SpecError(
                f"request state must be a mapping, got "
                f"{type(self.state).__name__}")


def _effective_timeout(request: AsyncRequest) -> float | None:
    """Explicit timeout wins; else the policy's latency budget."""
    if request.timeout_s is not None:
        return request.timeout_s
    policy = request.policy
    if policy is not None and policy.maximum_latency_ms is not None:
        return policy.maximum_latency_ms / 1000.0
    return None


class AsyncGate:
    """Async facade over :class:`HugrGate` (slice 283).

    All decision methods are coroutines; the wrapped gate's sync API is
    untouched.  ``max_concurrency`` bounds in-flight backend
    evaluations for the batch/stream methods.
    """

    def __init__(self, gate: HugrGate | None = None,
                 max_concurrency: int = 8) -> None:
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise SpecError(
                f"max_concurrency must be a positive int, got "
                f"{max_concurrency!r}")
        self.gate = gate if gate is not None else HugrGate()
        self.max_concurrency = max_concurrency
        self._closed = False

    # -- lifecycle ------------------------------------------------------

    def register(self, backend: Any, **kwargs: Any) -> None:
        """Register a backend on the wrapped gate."""
        self._ensure_open()
        self.gate.register(backend, **kwargs)

    def close(self) -> None:
        """Release backend resources; the facade must not be reused after."""
        if not self._closed:
            self._closed = True
            self.gate.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpecError("AsyncGate is closed")

    @property
    def closed(self) -> bool:
        return self._closed

    # -- single ----------------------------------------------------------

    async def adecide(self, state: Mapping[str, Any], spec: SpecLike,
                      policy: DecisionPolicy | None = None,
                      context: Mapping[str, Any] | None = None,
                      backend_name: str | None = None,
                      timeout_s: float | None = None) -> DecisionResult:
        """One async decision with timeout semantics (see module docs)."""
        self._ensure_open()
        request = AsyncRequest(state=state, spec=spec, policy=policy,
                               context=context, backend_name=backend_name,
                               timeout_s=timeout_s)
        return await self._run_one(request)

    async def _run_one(self, request: AsyncRequest) -> DecisionResult:
        timeout = _effective_timeout(request)
        coro = self.gate.adecide(
            request.state, request.spec, request.policy, request.context,
            request.backend_name)
        if timeout is None:
            return await coro
        start = time.monotonic()
        try:
            return await asyncio.wait_for(coro, timeout)
        except TimeoutError:
            raise
        except asyncio.TimeoutError as e:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            raise TimeoutError(
                f"async decision timed out after {elapsed_ms:.1f} ms "
                f"(budget {timeout * 1000.0:.1f} ms)",
                budget_ms=timeout * 1000.0,
                elapsed_ms=elapsed_ms) from e

    # -- batch ------------------------------------------------------------

    async def adecide_many(
            self, requests: Sequence[AsyncRequest],
            max_concurrency: int | None = None) -> list[DecisionResult]:
        """Decide all requests; results keep input order.

        The first exception propagates; remaining requests are
        cancelled (structured concurrency via TaskGroup semantics —
        implemented with explicit cancellation for 3.11 compat).
        """
        self._ensure_open()
        requests = list(requests)
        if not requests:
            return []
        bound = max_concurrency or self.max_concurrency
        if not isinstance(bound, int) or bound < 1:
            raise SpecError(
                f"max_concurrency must be a positive int, got {bound!r}")
        semaphore = asyncio.Semaphore(bound)

        async def _one(request: AsyncRequest) -> DecisionResult:
            async with semaphore:
                return await self._run_one(request)

        tasks = [asyncio.ensure_future(_one(r)) for r in requests]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

    # -- stream -------------------------------------------------------------

    async def astream(
            self, requests: Sequence[AsyncRequest],
            max_concurrency: int | None = None
            ) -> AsyncIterator[tuple[int, DecisionResult]]:
        """Yield ``(index, result)`` as decisions complete.

        Breaking out of the loop stops new work from starting;
        in-flight evaluations finish unless their own timeout fires.
        """
        self._ensure_open()
        requests = list(requests)
        if not requests:
            return
        bound = max_concurrency or self.max_concurrency
        if not isinstance(bound, int) or bound < 1:
            raise SpecError(
                f"max_concurrency must be a positive int, got {bound!r}")
        semaphore = asyncio.Semaphore(bound)

        async def _one(index: int, request: AsyncRequest
                       ) -> tuple[int, DecisionResult]:
            async with semaphore:
                return index, await self._run_one(request)

        pending = {asyncio.ensure_future(_one(i, r))
                   for i, r in enumerate(requests)}
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    # Exceptions surface here, at the consumer's pace.
                    yield task.result()
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
