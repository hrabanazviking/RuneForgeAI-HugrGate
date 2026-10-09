"""Retry budgets: bounded retries for recoverable failures (slice 268).

Unbounded retry is a reliability hazard: a flapping backend turns one
bad call into a self-inflicted denial of service. A :class:`RetryBudget`
is a small fixed-window token bucket — the first attempt is always
free, every *retry* consumes one token, and when the tokens are gone
:func:`retry_with_budget` raises :class:`RetryBudgetExhausted`
(chaining the last failure) instead of hammering the backend forever.

The default retry policy retries taxonomy errors that declare
themselves ``recoverable`` (``BackendUnavailable``, ``TimeoutError``,
``QueueFull``…); argument errors (``SpecError``, ``PolicyError``,
``ChaosError``) propagate immediately and never consume budget.
Backoff is deliberately out of scope here — callers compose their own
delay; the budget only bounds *how many* retries, never *when*.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from hugrgate.errors import HugrGateError, RetryBudgetExhausted, SpecError

__all__ = ["RetryBudget", "default_retry_policy", "retry_with_budget"]

T = TypeVar("T")


def default_retry_policy(exc: BaseException) -> bool:
    """Retry recoverable taxonomy errors; never argument errors.

    ``RetryBudgetExhausted`` is excluded: a budget verdict is final at
    its own level (an outer budget may still retry the whole block).
    """
    return (
        isinstance(exc, HugrGateError)
        and exc.recoverable
        and not isinstance(exc, RetryBudgetExhausted)
    )


class RetryBudget:
    """Fixed-window token bucket bounding retries.

    ``max_retries`` tokens are available per ``window_s`` seconds; the
    window resets the first time a token is requested after it lapses.
    Thread-safe.
    """

    def __init__(self, max_retries: int, window_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if (isinstance(max_retries, bool) or not isinstance(max_retries, int)
                or max_retries < 0):
            raise SpecError(
                f"max_retries must be a non-negative int, got "
                f"{max_retries!r}")
        if window_s <= 0:
            raise SpecError(
                f"window_s must be positive, got {window_s!r}")
        self._max_retries = max_retries
        self._window_s = window_s
        self._clock = clock
        self._lock = threading.RLock()
        self._tokens = max_retries
        self._window_start = clock()
        self._consumed_total = 0

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def _refill(self) -> None:
        now = self._clock()
        if now - self._window_start >= self._window_s:
            self._tokens = self._max_retries
            self._window_start = now

    def acquire(self) -> bool:
        """Consume one retry token; ``False`` when the budget is spent."""
        with self._lock:
            self._refill()
            if self._tokens <= 0:
                return False
            self._tokens -= 1
            self._consumed_total += 1
            return True

    @property
    def remaining(self) -> int:
        """Tokens currently available (refills the window first)."""
        with self._lock:
            self._refill()
            return self._tokens

    def stats(self) -> dict[str, Any]:
        with self._lock:
            self._refill()
            return {"max_retries": self._max_retries,
                    "remaining": self._tokens,
                    "consumed_total": self._consumed_total,
                    "window_s": self._window_s}

    def __repr__(self) -> str:
        return (f"RetryBudget(max_retries={self._max_retries}, "
                f"remaining={self.remaining})")


def retry_with_budget(fn: Callable[[], T], budget: RetryBudget, *,
                      is_retryable: Callable[[BaseException], bool] | None = None,
                      on_retry: Callable[[int, BaseException], None] | None = None) -> T:
    """Call ``fn()``, retrying retryable failures while the budget lasts.

    The first attempt never consumes budget; each retry consumes one
    token. Non-retryable exceptions propagate immediately without
    touching the budget. When the budget is spent,
    :class:`RetryBudgetExhausted` is raised (chaining the last
    failure) with ``attempts`` and ``last_error_code`` details.
    ``on_retry(attempt_number, exc)`` fires before each retry.
    """
    if not isinstance(budget, RetryBudget):
        raise SpecError(
            f"budget must be a RetryBudget, got {type(budget).__name__}")
    policy = is_retryable or default_retry_policy
    attempts = 0
    while True:
        attempts += 1
        try:
            return fn()
        except Exception as e:
            if not policy(e):
                raise
            if not budget.acquire():
                raise RetryBudgetExhausted(
                    f"retry budget exhausted after {attempts} attempt(s); "
                    f"last failure: {type(e).__name__}: {e}",
                    attempts=attempts,
                    last_error_code=getattr(e, "code", None),
                ) from e
            if on_retry is not None:
                on_retry(attempts, e)
