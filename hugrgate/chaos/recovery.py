"""Recovery verification: post-fault probes (slice 271).

Disarming a fault is not the same as recovering from it. A backend
can be disarmed while its circuit breaker is still open, its cache
still poisoned, or its threads still wedged — declaring "healthy"
at disarm time is how incidents relapse. A :class:`RecoveryVerifier`
runs an ordered set of :class:`RecoveryProbe`\\ s *after* the fault
clears and reports ``recovered`` only when every probe passes.

Probes may need a few attempts: a restarted backend often needs a
moment to warm up. :meth:`RecoveryVerifier.verify` therefore takes
``max_attempts``/``wait_s`` (with an injectable clock/sleep so
tests stay fast and deterministic); the report records how many
attempts recovery took.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "RecoveryProbe",
    "RecoveryReport",
    "RecoveryVerifier",
    "backend_health_probe",
    "circuit_closed_probe",
    "decision_smoke_probe",
]

#: A probe: raises on failure, returns a human note on success.
ProbeCheck = Callable[[], str]

PASSED = "passed"
FAILED = "failed"


@dataclass(frozen=True)
class RecoveryProbe:
    """One post-fault check."""

    name: str
    description: str
    check: ProbeCheck

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("recovery probe name must be non-empty")
        if not callable(self.check):
            raise SpecError(
                f"recovery probe {self.name!r} check must be callable")


@dataclass
class _ProbeOutcome:
    name: str
    status: str
    note: str = ""
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status,
                "note": self.note, "attempts": self.attempts}


@dataclass
class RecoveryReport:
    """The verdict of a recovery verification run."""

    verifier_name: str
    probes: list[_ProbeOutcome]
    started_at: float
    finished_at: float

    @property
    def recovered(self) -> bool:
        return bool(self.probes) and all(
            p.status == PASSED for p in self.probes)

    @property
    def attempts(self) -> int:
        return max((p.attempts for p in self.probes), default=0)

    def to_dict(self) -> dict[str, Any]:
        report = {"verifier_name": self.verifier_name,
                  "recovered": self.recovered,
                  "attempts": self.attempts,
                  "probes": [p.to_dict() for p in self.probes],
                  "started_at": self.started_at,
                  "finished_at": self.finished_at,
                  "duration_s": self.finished_at - self.started_at}
        json.dumps(report)  # contract: always serializable
        return report


class RecoveryVerifier:
    """Ordered post-fault probes with a recovery verdict.

    ``verify`` runs every probe (a failing probe does not stop the
    others — a partial picture beats none). With ``max_attempts`` >
    1, each probe is retried after ``wait_s`` seconds until it
    passes; ``sleep`` is injectable for deterministic tests.
    """

    def __init__(self, name: str,
                 probes: list[RecoveryProbe] | tuple[RecoveryProbe, ...],
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not name.strip():
            raise SpecError("recovery verifier name must be non-empty")
        probes = list(probes)
        if not probes:
            raise SpecError(
                f"recovery verifier {name!r} needs at least one probe")
        names = [p.name for p in probes]
        if len(set(names)) != len(names):
            raise SpecError(
                f"recovery verifier {name!r} has duplicate probe names")
        self._name = name
        self._probes = probes
        self._sleep = sleep
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return self._name

    def probe_names(self) -> list[str]:
        return [p.name for p in self._probes]

    def verify(self, max_attempts: int = 1,
               wait_s: float = 0.0) -> RecoveryReport:
        if max_attempts < 1:
            raise SpecError(
                f"max_attempts must be >= 1, got {max_attempts!r}")
        if wait_s < 0:
            raise SpecError(f"wait_s must be >= 0, got {wait_s!r}")
        started = time.monotonic()
        outcomes: list[_ProbeOutcome] = []
        with self._lock:
            probes = list(self._probes)
        for probe in probes:
            attempts = 0
            note = ""
            while True:
                attempts += 1
                try:
                    note = probe.check()
                except Exception as e:  # noqa: BLE001 - recorded
                    note = f"{type(e).__name__}: {e}"
                    if attempts >= max_attempts:
                        outcomes.append(_ProbeOutcome(
                            probe.name, FAILED, note, attempts))
                        break
                    self._sleep(wait_s)
                else:
                    outcomes.append(_ProbeOutcome(
                        probe.name, PASSED, note, attempts))
                    break
        return RecoveryReport(
            verifier_name=self._name, probes=outcomes,
            started_at=started, finished_at=time.monotonic())


# --- builtin probes (real collaborators, no mocks) -------------------------------------

def backend_health_probe(backend: Any) -> RecoveryProbe:
    """Probe that passes when ``backend.health()`` reports ok."""

    def check() -> str:
        health = backend.health()
        status = health.get("status")
        if status != "ok":
            raise AssertionError(
                f"backend {backend.name!r} health status {status!r}: "
                f"{health}")
        return f"backend {backend.name!r} reports healthy"

    return RecoveryProbe(
        name=f"backend-health:{backend.name}",
        description="Backend health() reports ok.",
        check=check)


def decision_smoke_probe(gate: Any, state: Mapping[str, Any],
                         spec: Any, backend_name: str | None = None
                         ) -> RecoveryProbe:
    """Probe that passes when a real ``decide()`` succeeds."""

    def check() -> str:
        result = gate.decide(dict(state), spec, backend_name=backend_name)
        if not result.accepted:
            raise AssertionError(
                f"smoke decision not accepted: {result}")
        return (f"smoke decision accepted "
                f"(value={result.value!r}, backend={result.backend!r})")

    return RecoveryProbe(
        name="decision-smoke",
        description="A real decide() call succeeds and is accepted.",
        check=check)


def circuit_closed_probe(get_state: Callable[[], str],
                         backend_name: str) -> RecoveryProbe:
    """Probe that passes when the breaker's state for the backend is
    closed. ``get_state`` returns the breaker state string."""

    def check() -> str:
        state = get_state()
        if state != "closed":
            raise AssertionError(
                f"circuit for {backend_name!r} is {state!r}, not closed")
        return f"circuit for {backend_name!r} is closed"

    return RecoveryProbe(
        name=f"circuit-closed:{backend_name}",
        description="Circuit breaker for the backend is closed.",
        check=check)
