"""Resource-exhaustion guards. Slice 410.

Input-size limits (slice 409) bound the *shape* of one request;
this module bounds what a request may *consume* while running
(threat T-04, second half):

- :class:`ResourceBudget` + :func:`guarded` — real OS enforcement
  via ``resource.setrlimit``: ``RLIMIT_CPU`` (SIGXCPU converted to
  :class:`ResourceBudgetExceeded`) and ``RLIMIT_AS`` (allocation
  failures beyond the address-space cap surface as
  :class:`ResourceBudgetExceeded`). Previous limits and signal
  handlers are restored on exit.
- :class:`CostLedger` — cooperative cost accounting for
  algorithmic-complexity hazards (batch fan-out, regex backtracking
  budgets, recursion): :meth:`CostLedger.charge` raises when the
  charged units exceed the budget.

POSIX-only: where the ``resource`` module is unavailable the OS
guard degrades to a documented no-op (``enforced=False``) while
the ledger keeps working — see law 13 in the roadmap.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import ResourceBudgetExceeded

__all__ = [
    "CostLedger",
    "ResourceBudget",
    "guarded",
    "posix_available",
]

try:
    import resource as _resource
except ImportError:  # pragma: no cover - non-POSIX platforms
    _resource = None  # type: ignore[assignment]


def posix_available() -> bool:
    """Whether OS-level (rlimit) enforcement is available."""
    return _resource is not None and hasattr(signal, "SIGXCPU")


@dataclass(frozen=True)
class ResourceBudget:
    """Hard caps for one guarded region."""

    max_cpu_seconds: float | None = None
    max_rss_bytes: int | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_rss_bytes": self.max_rss_bytes,
            "enforced": posix_available(),
        }


def _current_rss() -> int:
    if _resource is None:  # pragma: no cover
        return 0
    # ru_maxrss is kilobytes on Linux.
    return _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss * 1024


def _raise_cpu_exceeded(signum: int, frame: Any) -> None:
    raise ResourceBudgetExceeded(
        "CPU time budget exceeded inside guarded region",
        limit="max_cpu_seconds")


@contextmanager
def guarded(budget: ResourceBudget) -> Iterator[ResourceBudget]:
    """Enforce ``budget`` for the block; restore everything after."""
    if not posix_available():
        yield budget  # documented no-op off POSIX
        return
    assert _resource is not None
    old_cpu = _resource.getrlimit(_resource.RLIMIT_CPU)
    old_as = _resource.getrlimit(_resource.RLIMIT_AS)
    old_handler = signal.getsignal(signal.SIGXCPU)
    cpu_seconds = (int(budget.max_cpu_seconds)
                   if budget.max_cpu_seconds else -1)
    try:
        if budget.max_cpu_seconds:
            # Soft limit -> SIGXCPU (catchable); hard limit kills.
            _resource.setrlimit(
                _resource.RLIMIT_CPU,
                (cpu_seconds, old_cpu[1]))
            signal.signal(signal.SIGXCPU, _raise_cpu_exceeded)
        if budget.max_rss_bytes:
            _resource.setrlimit(
                _resource.RLIMIT_AS,
                (budget.max_rss_bytes, old_as[1]))
        yield budget
    except MemoryError as e:
        # Allocation failed while the address-space cap was armed:
        # attribute it to the budget (checked against observed peak).
        raise ResourceBudgetExceeded(
            "address-space budget exceeded inside guarded region",
            limit="max_rss_bytes",
            peak_rss_bytes=_current_rss()) from e
    finally:
        _resource.setrlimit(_resource.RLIMIT_CPU, old_cpu)
        _resource.setrlimit(_resource.RLIMIT_AS, old_as)
        signal.signal(signal.SIGXCPU, old_handler)


class CostLedger:
    """Cooperative cost accounting for algorithmic-complexity hazards.

    Call :meth:`charge` as work fans out (batch items, regex steps,
    expanded templates); exceeding the budget raises immediately
    with the running total attached. Thread-safe.
    """

    def __init__(self, budget_units: int, name: str = "cost") -> None:
        if budget_units < 1:
            raise ValueError("budget_units must be >= 1")
        self._budget = budget_units
        self._name = name
        self._spent = 0
        self._lock = threading.Lock()

    @property
    def spent(self) -> int:
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self._budget - self._spent)

    def charge(self, units: int, what: str = "") -> int:
        """Charge ``units``; returns the new total spent."""
        if units < 0:
            raise ValueError("cannot charge negative units")
        with self._lock:
            self._spent += units
            spent = self._spent
        if spent > self._budget:
            raise ResourceBudgetExceeded(
                f"cost budget exceeded for {self._name}: "
                f"{spent} > {self._budget}",
                limit=self._name, spent=spent,
                budget=self._budget, what=what)
        return spent

    def describe(self) -> dict[str, Any]:
        return {"name": self._name, "budget": self._budget,
                "spent": self.spent, "remaining": self.remaining}
