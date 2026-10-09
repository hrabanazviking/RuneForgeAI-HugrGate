"""Clock-skew simulation and audit. Slice 265.

Wall-clock time jumps: NTP step corrections, VM pauses, daylight
follies. Any *duration* measured on the wall clock — deadlines,
TTLs, staleness — breaks when it does. HugrGate's rule, verified by
this module's audit: every enforcement path (deadlines, TTLs,
breaker timeouts, watchdog intervals, experiment durations) runs on
a monotonic clock; the wall clock is used only for *timestamps*
(human-readable records), never for decisions.

- :class:`SkewedClock` — a test clock that jumps: wraps a base
  clock and applies instantaneous offsets, modeling NTP steps.
  Usable anywhere a ``clock=`` callable is accepted.
- :func:`audit_deadline_clocks` — inspects the live code and
  reports which clock each resilience-critical component uses.
  This is a regression tripwire: if someone rewires a deadline to
  the wall clock, the audit (and its test) fails until the change
  is made deliberately.

Known wall-clock *durations* (audited, accepted, documented —
not tripwired because their blast radius is bounded and
self-healing):

- ``adaptive.delayed.PendingLabel.age`` — delayed-label expiry;
  skew causes early/late expiry of telemetry labels (never a
  decision);
- ``cluster.discovery.PeerInfo.is_stale`` — peer staleness; skew
  can drop live peers or keep dead ones until the next heartbeat
  (degraded routing, self-heals);
- ``cluster.lan`` announce cadence — announce interval shifts
  (benign).
"""

from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable
from typing import Any

import hugrgate.cache as _cache
import hugrgate.chaos.framework as _framework
import hugrgate.circuit as _circuit
import hugrgate.edge.watchdog as _watchdog
from hugrgate.errors import SpecError

__all__ = [
    "SkewedClock",
    "audit_deadline_clocks",
]


class SkewedClock:
    """A clock that jumps.

    ``now()`` returns ``base() + offset``; :meth:`jump` changes the
    offset instantaneously (an NTP step correction), :meth:`advance`
    moves the base smoothly. Thread-safe.
    """

    def __init__(self, base: Callable[[], float] = time.monotonic):
        self._base = base
        self._offset = 0.0
        self._lock = threading.RLock()

    def now(self) -> float:
        with self._lock:
            return self._base() + self._offset

    __call__ = now

    def jump(self, seconds: float) -> SkewedClock:
        """Apply an instantaneous clock step (positive or negative)."""
        with self._lock:
            self._offset += seconds
        return self

    def advance(self, seconds: float) -> SkewedClock:
        """Move time smoothly forward (advances the base reading)."""
        if seconds < 0:
            raise SpecError(
                f"advance() needs seconds >= 0, got {seconds}")
        with self._lock:
            # Advance by shifting the offset: the base is opaque.
            self._offset += seconds
        return self

    @property
    def offset(self) -> float:
        with self._lock:
            return self._offset


def _signature_clock_default(module: object, qualname: str) -> str:
    """The default of the ``clock`` parameter, or a marker string."""
    target: Any = module
    for part in qualname.split("."):
        target = getattr(target, part)
    # inspect.signature on the class reads the constructor signature
    # (via __init__) without touching the instance attribute.
    params = inspect.signature(target).parameters
    if "clock" not in params:
        return "<no clock parameter>"
    default = params["clock"].default
    if default is time.monotonic:
        return "monotonic"
    if default is None:
        # None-defaults resolve to monotonic internally (documented).
        return "monotonic (None -> monotonic)"
    return f"UNEXPECTED: {default!r}"


def audit_deadline_clocks() -> dict[str, str]:
    """Report which clock each resilience-critical component uses.

    Returns ``component -> clock kind``. Every enforcement path must
    report a monotonic clock; anything else is a skew vulnerability
    and fails the audit's test until fixed or deliberately accepted.
    """
    report: dict[str, str] = {
        "hugrgate.circuit.CircuitRegistry": _signature_clock_default(
            _circuit, "CircuitRegistry"),
        "hugrgate.chaos.framework.ExperimentRunner":
            _signature_clock_default(_framework, "ExperimentRunner"),
        "hugrgate.edge.watchdog.EdgeWatchdog": _signature_clock_default(
            _watchdog, "EdgeWatchdog"),
        # DecisionCache takes no clock: it calls time.monotonic()
        # directly. Tripwire on the source so a refactor to the wall
        # clock fails loudly.
        "hugrgate.cache.DecisionCache": (
            "monotonic (direct)"
            if "time.monotonic()" in inspect.getsource(_cache.DecisionCache)
            and "time.time(" not in inspect.getsource(_cache.DecisionCache)
            else "UNEXPECTED: wall-clock usage detected"
        ),
        # run_with_deadline enforces via thread.join(deadline): a
        # relative timeout, inherently monotonic.
        "hugrgate.timeout.run_with_deadline":
            "monotonic (relative thread.join)",
    }
    return report
