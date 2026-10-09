"""Rollback triggers. Slice 469.

The canary driver (slice 468) has the *mechanism* for rollback; this
module adds the *policy*: declarative triggers that watch metrics and
fire automatically.

A :class:`RollbackTrigger` watches one metric callable and fires when
the metric stays on the wrong side of a threshold for
``sustained`` consecutive checks — a single bad sample never pages
anyone. :class:`RollbackController.check()` evaluates all triggers,
tracks consecutive breaches, and on firing calls the registered
``restore`` function (e.g. restoring the pre-canary snapshot). If the
restore itself fails, :class:`RollbackError` is raised — a failed
rollback is a state-integrity emergency, never retried blindly.

:meth:`RollbackController.as_canary_guardrails` converts triggers
into the ``(ok, reason)`` guardrail callables
:class:`CanaryDriver` polls, wiring this slice to slice 468. A
firing trigger reports breach (not ok) exactly once per arming; after
firing it disarms until :meth:`reset` (operators re-arm deliberately).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import RollbackError

__all__ = [
    "RollbackController",
    "RollbackEvent",
    "RollbackTrigger",
]


@dataclass(frozen=True)
class RollbackTrigger:
    """One watched metric with a sustained-breach condition."""

    name: str
    metric: Callable[[], float]
    direction: str  # "gt": fire when metric > threshold; "lt": <
    threshold: float
    sustained: int = 3
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise RollbackError("trigger needs a name")
        if self.direction not in ("gt", "lt"):
            raise RollbackError("direction must be gt/lt",
                                trigger=self.name)
        if self.sustained < 1:
            raise RollbackError("sustained must be >= 1",
                                trigger=self.name)

    def breached(self) -> bool:
        try:
            value = float(self.metric())
        except Exception as exc:  # fail closed: unreadable metric is a breach
            raise RollbackError("trigger metric raised",
                                trigger=self.name,
                                error=repr(exc)) from exc
        return value > self.threshold if self.direction == "gt" \
            else value < self.threshold


@dataclass
class RollbackEvent:
    """One fired trigger."""

    trigger: str
    fired_at: float
    breaches: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"trigger": self.trigger, "fired_at": self.fired_at,
                "breaches": self.breaches, "reason": self.reason}


class RollbackController:
    """Evaluate triggers; fire restores; journal everything."""

    def __init__(self,
                 restore: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._triggers: dict[str, RollbackTrigger] = {}
        self._breach_counts: dict[str, int] = {}
        self._disarmed: set[str] = set()
        self._events: list[RollbackEvent] = []
        self._restore = restore
        self._clock = clock

    def add_trigger(self, trigger: RollbackTrigger) -> None:
        if trigger.name in self._triggers:
            raise RollbackError("duplicate trigger", trigger=trigger.name)
        self._triggers[trigger.name] = trigger
        self._breach_counts[trigger.name] = 0

    def reset(self, name: str) -> None:
        """Re-arm a fired trigger and clear its breach count."""
        if name not in self._triggers:
            raise RollbackError("unknown trigger", trigger=name)
        self._disarmed.discard(name)
        self._breach_counts[name] = 0

    @property
    def events(self) -> list[RollbackEvent]:
        return list(self._events)

    def evaluate(self) -> list[RollbackEvent]:
        """Update breach counts; return events that would fire now."""
        due: list[RollbackEvent] = []
        for name, trigger in self._triggers.items():
            if name in self._disarmed:
                continue
            if trigger.breached():
                self._breach_counts[name] += 1
            else:
                self._breach_counts[name] = 0
            if self._breach_counts[name] >= trigger.sustained:
                due.append(RollbackEvent(
                    trigger=name, fired_at=self._clock(),
                    breaches=self._breach_counts[name],
                    reason=(f"{trigger.description or name}: metric "
                            f"{'above' if trigger.direction == 'gt' else 'below'} "
                            f"{trigger.threshold} for "
                            f"{self._breach_counts[name]} checks")))
        return due

    def check(self) -> list[RollbackEvent]:
        """Evaluate every armed trigger; fire restores on sustained breach."""
        fired = self.evaluate()
        for event in fired:
            self._fire(event)
        return fired

    def _record(self, event: RollbackEvent) -> None:
        self._disarmed.add(event.trigger)
        self._breach_counts[event.trigger] = 0
        self._events.append(event)

    def _fire(self, event: RollbackEvent) -> None:
        if self._restore is None:
            raise RollbackError("no restore function registered",
                                trigger=event.trigger)
        try:
            self._restore()
        except Exception as exc:
            raise RollbackError("rollback restore failed",
                                trigger=event.trigger,
                                error=repr(exc)) from exc
        self._record(event)

    def as_canary_guardrails(
            self) -> list[Callable[[], tuple[bool, str]]]:
        """Trigger set as :class:`CanaryDriver` guardrail callables.

        The guard evaluates (no restore of its own): on breach it
        records the event and reports not-ok, and the *driver*
        performs the rollback via its lease snapshot. Exactly one
        restore happens, owned by the driver.
        """
        def _guard() -> tuple[bool, str]:
            due = self.evaluate()
            for event in due:
                self._record(event)
            if due:
                return False, "; ".join(e.reason for e in due)
            return True, "triggers armed"
        return [_guard]
