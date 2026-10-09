"""Long soak: sustained load + scheduled faults + invariants (slice 273).

A soak test answers "does the system stay healthy over time, not
just at instants?" :class:`SoakRunner` drives a workload at a
target rate for a duration, applies and reverts scheduled faults
mid-run (via the chaos toolkit), checks invariants periodically,
and reports. The soak passes when no invariant is violated and no
*unexpected* error type appears — expected fault-induced errors
(e.g. ``BackendError`` under an armed ``error_rate`` fault) are
counted, not failed.

Small by default (``duration_s=2.0``): the point of the committed
test is the machinery and the invariants, not burning CI hours.
Longer soaks are one argument away. Single-threaded and
deterministic by construction.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SpecError

__all__ = ["ScheduledFault", "SoakConfig", "SoakReport", "SoakRunner"]


@dataclass(frozen=True)
class ScheduledFault:
    """A fault applied at ``at_s`` and reverted at ``until_s``."""

    name: str
    at_s: float
    until_s: float
    apply: Callable[[], None]
    revert: Callable[[], None]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("scheduled fault name must be non-empty")
        if not 0 <= self.at_s < self.until_s:
            raise SpecError(
                f"scheduled fault {self.name!r} needs "
                f"0 <= at_s < until_s, got {self.at_s}, {self.until_s}")


@dataclass(frozen=True)
class SoakConfig:
    """How long and how hard to soak."""

    duration_s: float = 2.0
    target_ops_per_s: float = 50.0
    max_ops: int | None = None
    invariant_every_n_ops: int = 25
    expected_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_s <= 0:
            raise SpecError(
                f"duration_s must be positive, got {self.duration_s!r}")
        if self.target_ops_per_s <= 0:
            raise SpecError(
                "target_ops_per_s must be positive, got "
                f"{self.target_ops_per_s!r}")
        if self.max_ops is not None and self.max_ops < 1:
            raise SpecError(
                f"max_ops must be >= 1, got {self.max_ops!r}")
        if self.invariant_every_n_ops < 1:
            raise SpecError(
                "invariant_every_n_ops must be >= 1, got "
                f"{self.invariant_every_n_ops!r}")


@dataclass
class SoakReport:
    """What the soak observed."""

    ops_completed: int
    errors: dict[str, int]
    unexpected_errors: dict[str, int]
    violations: list[str]
    faults_applied: list[str]
    duration_s: float

    @property
    def passed(self) -> bool:
        return not self.violations and not self.unexpected_errors

    def to_dict(self) -> dict[str, Any]:
        report = {"ops_completed": self.ops_completed,
                  "errors": self.errors,
                  "unexpected_errors": self.unexpected_errors,
                  "violations": self.violations,
                  "faults_applied": self.faults_applied,
                  "duration_s": self.duration_s,
                  "passed": self.passed}
        json.dumps(report)  # contract: always serializable
        return report


class SoakRunner:
    """Drive ``workload`` under scheduled faults, checking invariants.

    ``workload(op_index)`` performs one unit of work; per-op
    exceptions are counted by type name. ``invariants`` are zero-arg
    callables run every ``invariant_every_n_ops`` ops; a raising
    invariant is a recorded violation (the soak continues).
    ``faults`` are applied/reverted on schedule. Thread-safe
    counters; the run itself is single-threaded.
    """

    def __init__(self,
                 workload: Callable[[int], None],
                 invariants: list[Callable[[], None]] | None = None,
                 faults: list[ScheduledFault] | None = None) -> None:
        if not callable(workload):
            raise SpecError("soak workload must be callable")
        self._workload = workload
        self._invariants = list(invariants or [])
        for inv in self._invariants:
            if not callable(inv):
                raise SpecError("soak invariants must be callable")
        self._faults = sorted(faults or [], key=lambda f: f.at_s)
        names = [f.name for f in self._faults]
        if len(set(names)) != len(names):
            raise SpecError("duplicate scheduled fault names")
        self._lock = threading.Lock()

    def run(self, config: SoakConfig | None = None) -> SoakReport:
        config = config or SoakConfig()
        start = time.monotonic()
        deadline = start + config.duration_s
        period = 1.0 / config.target_ops_per_s
        next_op_at = start
        ops = 0
        errors: dict[str, int] = {}
        violations: list[str] = []
        faults_applied: list[str] = []
        active: list[ScheduledFault] = []
        pending = list(self._faults)

        def note_error(e: BaseException) -> None:
            name = type(e).__name__
            with self._lock:
                errors[name] = errors.get(name, 0) + 1

        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            if config.max_ops is not None and ops >= config.max_ops:
                break
            # Fault schedule.
            elapsed = now - start
            while pending and pending[0].at_s <= elapsed:
                fault = pending.pop(0)
                fault.apply()
                active.append(fault)
                faults_applied.append(fault.name)
            for fault in [f for f in active if f.until_s <= elapsed]:
                fault.revert()
                active.remove(fault)
            # One unit of work.
            try:
                self._workload(ops)
            except Exception as e:  # noqa: BLE001 - counted per op
                note_error(e)
            ops += 1
            if ops % config.invariant_every_n_ops == 0:
                for inv in self._invariants:
                    try:
                        inv()
                    except Exception as e:  # noqa: BLE001 - recorded
                        violations.append(
                            f"op {ops}: {type(e).__name__}: {e}")
            # Pace to the target rate.
            next_op_at += period
            delay = next_op_at - time.monotonic()
            if delay > 0:
                time.sleep(min(delay, 0.05))
            else:
                next_op_at = time.monotonic()
        for fault in active:  # never leave a fault armed
            fault.revert()
        duration_s = time.monotonic() - start
        unexpected = {k: v for k, v in errors.items()
                      if k not in config.expected_errors}
        return SoakReport(
            ops_completed=ops, errors=errors,
            unexpected_errors=unexpected, violations=violations,
            faults_applied=faults_applied, duration_s=duration_s)
