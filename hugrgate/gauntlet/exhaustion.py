"""Resource exhaustion gauntlet (slice 492).

Input limits existed (``hugrgate/security/input_limits.py``) but
``HugrGate.decide_batch`` never called ``check_batch`` — an
unbounded batch fanned out without limit (fixed in slice 492).
This module is the gauntlet proving exhaustion scenarios are
contained end to end through the live gate:

- oversized / over-deep / non-serializable states → ``SpecError``
  via :meth:`HugrGate.decide`;
- oversized batches (count or total bytes) → ``InputTooLarge``
  via :meth:`HugrGate.decide_batch`;
- after every rejection the gate still serves (no poisoning);
- a control batch passes untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import InputTooLarge, SpecError

__all__ = [
    "ExhaustionReport",
    "run_exhaustion_gauntlet",
]


@dataclass
class ExhaustionReport:
    """Outcome of :func:`run_exhaustion_gauntlet`."""

    scenarios: list[dict[str, Any]] = field(default_factory=list)

    @property
    def contained(self) -> bool:
        return bool(self.scenarios) and all(
            s["contained"] for s in self.scenarios)


def _scenario(report: ExhaustionReport, name: str, func: Any,
              expect: type[BaseException] | None) -> None:
    try:
        func()
    except expect as exc:  # type: ignore[misc]
        report.scenarios.append({"name": name, "contained": True,
                                 "error": type(exc).__name__})
    except Exception as exc:  # noqa: BLE001 - wrong-kind escape
        report.scenarios.append({"name": name, "contained": False,
                                 "error": f"WRONG KIND: {type(exc).__name__}"})
    else:
        report.scenarios.append({"name": name,
                                 "contained": expect is None,
                                 "error": None})


def run_exhaustion_gauntlet(gate: Any, spec: Any, policy: Any) -> ExhaustionReport:
    """Run the exhaustion battery against a live ``HugrGate``."""
    report = ExhaustionReport()
    ok_state = {"x": 1}

    _scenario(report, "oversized state",
              lambda: gate.decide({"blob": "x" * 2_000_000}, spec, policy),
              SpecError)
    deep: dict[str, Any] = {}
    cursor = deep
    for _ in range(100):
        cursor["n"] = {}
        cursor = cursor["n"]
    _scenario(report, "over-deep state",
              lambda: gate.decide(deep, spec, policy), SpecError)
    _scenario(report, "non-serializable state",
              lambda: gate.decide({"x": object()}, spec, policy), SpecError)
    _scenario(report, "oversized batch (count)",
              lambda: gate.decide_batch([ok_state] * 2000, spec, policy),
              InputTooLarge)
    _scenario(report, "oversized batch (bytes)",
              lambda: gate.decide_batch(
                  [{"blob": "y" * 900_000}] * 6, spec, policy),
              InputTooLarge)

    def _control() -> None:
        results = gate.decide_batch([ok_state] * 4, spec, policy)
        assert len(results) == 4

    _scenario(report, "control batch", _control, None)

    def _still_alive() -> None:
        gate.decide(ok_state, spec, policy)

    _scenario(report, "gate alive after battery", _still_alive, None)
    return report
