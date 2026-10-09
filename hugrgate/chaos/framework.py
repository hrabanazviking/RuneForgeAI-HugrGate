"""Chaos experiment framework. Slice 251.

A chaos experiment is a *falsifiable* claim about resilience, not a
script that breaks things and hopes. The model:

- :class:`ChaosExperiment` states a **hypothesis**
  ("the fallback chain survives a backend crash") and the
  **steady-state probes** that define "healthy";
- :class:`Fault` describes one injected failure: ``inject`` breaks,
  ``verify`` asserts the documented degradation held, ``rollback``
  restores the world. Injection and verification are separate
  callables so a broken injector cannot masquerade as a passing
  verification;
- :class:`BlastRadius` is the safety interlock: faults run only
  against named, allow-listed targets, with an optional dry-run mode
  that verifies and rolls back without ever injecting;
- :class:`ExperimentRunner` executes the experiment and **records
  every outcome** — a raising fault, a failed verification, or a
  rollback error is a recorded failure, never an abort. The report
  must show *all* outcomes.

Probes run before any fault and again after the last rollback; a
steady-state delta means the experiment itself leaked damage, which
is reported as a failure even when every fault "passed".

Every fault receives a context dict carrying a seeded
``random.Random`` under ``"rng"`` (``experiment.seed``), so fault
sequences are reproducible. ``seed=None`` uses system entropy and is
recorded as such in the report.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ChaosError

__all__ = [
    "BlastRadius",
    "ChaosExperiment",
    "ExperimentReport",
    "ExperimentRunner",
    "Fault",
    "FaultResult",
    "ProbeOutcome",
    "SteadyStateProbe",
]


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of one steady-state probe."""

    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class SteadyStateProbe:
    """A named health definition: "what does healthy look like?"."""

    name: str
    check: Callable[[], ProbeOutcome]
    """Return a ProbeOutcome; raising counts as not-ok."""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ChaosError("probe name must be non-empty")

    def run(self) -> ProbeOutcome:
        try:
            outcome = self.check()
        except Exception as e:  # noqa: BLE001 - probe failure is data
            return ProbeOutcome(False, f"{type(e).__name__}: {e}")
        if not isinstance(outcome, ProbeOutcome):
            raise ChaosError(
                f"probe {self.name!r} must return ProbeOutcome, "
                f"got {type(outcome).__name__}")
        return outcome


@dataclass(frozen=True)
class Fault:
    """One injected failure with verification and rollback.

    ``inject`` receives the experiment context and breaks the target;
    ``verify`` asserts the documented degradation behavior held
    (raises on failure); ``rollback`` restores the target and may be
    ``None`` when the fault is self-contained.
    """

    name: str
    description: str
    inject: Callable[[dict[str, Any]], None]
    verify: Callable[[dict[str, Any]], None]
    rollback: Callable[[dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ChaosError("fault name must be non-empty")
        if not self.description.strip():
            raise ChaosError("fault description must be non-empty")


@dataclass(frozen=True)
class FaultResult:
    """Outcome of one fault's inject/verify/rollback cycle."""

    name: str
    injected: bool
    verified: bool
    rolled_back: bool
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.injected and self.verified and self.rolled_back

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "injected": self.injected,
            "verified": self.verified,
            "rolled_back": self.rolled_back,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BlastRadius:
    """Safety interlock: faults run only against allow-listed targets.

    ``allowed_targets`` is the exact set of target names the experiment
    may touch. ``dry_run=True`` verifies and rolls back without ever
    calling ``inject`` — useful for rehearsing an experiment.
    """

    allowed_targets: frozenset[str] = frozenset()
    dry_run: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "allowed_targets", frozenset(self.allowed_targets))

    def check(self, target: str) -> None:
        if target not in self.allowed_targets:
            raise ChaosError(
                f"target {target!r} is outside the experiment blast radius "
                f"(allowed: {sorted(self.allowed_targets)})")


@dataclass(frozen=True)
class ChaosExperiment:
    """A falsifiable resilience claim with its fault plan."""

    name: str
    hypothesis: str
    faults: tuple[Fault, ...] = ()
    probes: tuple[SteadyStateProbe, ...] = ()
    blast_radius: BlastRadius = field(default_factory=BlastRadius)
    seed: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ChaosError("experiment name must be non-empty")
        if not self.hypothesis.strip():
            raise ChaosError("experiment hypothesis must be non-empty")
        if not self.faults:
            raise ChaosError("experiment must declare at least one fault")
        names = [f.name for f in self.faults]
        if len(set(names)) != len(names):
            raise ChaosError(f"duplicate fault names in experiment: {names}")
        object.__setattr__(self, "faults", tuple(self.faults))
        object.__setattr__(self, "probes", tuple(self.probes))


@dataclass
class ExperimentReport:
    """Full outcome of one experiment run. JSON-serializable."""

    experiment: str
    hypothesis: str
    target: str
    seed: int | None
    dry_run: bool
    steady_before: dict[str, ProbeOutcome] = field(default_factory=dict)
    steady_after: dict[str, ProbeOutcome] = field(default_factory=dict)
    faults: list[FaultResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def steady_state_held(self) -> bool:
        """Every probe ok before AND after, with no new failures."""
        before_ok = all(o.ok for o in self.steady_before.values())
        after_ok = all(o.ok for o in self.steady_after.values())
        return before_ok and after_ok and bool(self.steady_before)

    @property
    def all_passed(self) -> bool:
        return (all(f.passed for f in self.faults)
                and self.steady_state_held
                and bool(self.faults))

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment,
            "hypothesis": self.hypothesis,
            "target": self.target,
            "seed": self.seed,
            "dry_run": self.dry_run,
            "steady_state_held": self.steady_state_held,
            "steady_before": {n: o.to_dict()
                              for n, o in self.steady_before.items()},
            "steady_after": {n: o.to_dict()
                             for n, o in self.steady_after.items()},
            "faults": [f.to_dict() for f in self.faults],
            "all_passed": self.all_passed,
            "duration_s": self.finished_at - self.started_at,
        }


class ExperimentRunner:
    """Executes chaos experiments against named targets.

    Thread-safe; experiments are hermetic by construction (each fault
    gets a fresh context dict). A fault that raises during inject,
    verify, or rollback is recorded — the run continues so the report
    shows every outcome.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.RLock()
        self._reports: dict[str, ExperimentReport] = {}
        self._clock = clock

    def run(self, experiment: ChaosExperiment, target: str) -> ExperimentReport:
        experiment.blast_radius.check(target)
        report = ExperimentReport(
            experiment=experiment.name,
            hypothesis=experiment.hypothesis,
            target=target,
            seed=experiment.seed,
            dry_run=experiment.blast_radius.dry_run,
            started_at=self._clock(),
        )
        report.steady_before = self._run_probes(experiment.probes)
        context: dict[str, Any] = {
            "experiment": experiment.name,
            "target": target,
            "rng": random.Random(experiment.seed),
            "dry_run": experiment.blast_radius.dry_run,
        }
        for fault in experiment.faults:
            report.faults.append(self._run_fault(fault, context))
        report.steady_after = self._run_probes(experiment.probes)
        report.finished_at = self._clock()
        with self._lock:
            self._reports[experiment.name] = report
        return report

    def last_report(self, experiment_name: str) -> ExperimentReport | None:
        with self._lock:
            return self._reports.get(experiment_name)

    @staticmethod
    def _run_probes(
            probes: tuple[SteadyStateProbe, ...]) -> dict[str, ProbeOutcome]:
        return {p.name: p.run() for p in probes}

    def _run_fault(self, fault: Fault,
                   context: Mapping[str, Any]) -> FaultResult:
        ctx = dict(context)
        detail = ""
        # --- inject ---------------------------------------------------
        if ctx.get("dry_run"):
            injected = True
            detail = "dry-run: injection skipped"
        else:
            try:
                fault.inject(ctx)
            except Exception as e:  # noqa: BLE001 - recorded per fault
                return FaultResult(fault.name, False, False, True,
                                   f"inject failed: {type(e).__name__}: {e}")
            injected = True
        # --- verify ---------------------------------------------------
        try:
            fault.verify(ctx)
        except Exception as e:  # noqa: BLE001 - recorded per fault
            verified = False
            detail = (detail + "; " if detail else "") + \
                f"verify failed: {type(e).__name__}: {e}"
        else:
            verified = True
        # --- rollback -------------------------------------------------
        rolled_back = True
        if fault.rollback is not None:
            try:
                fault.rollback(ctx)
            except Exception as e:  # noqa: BLE001 - recorded per fault
                rolled_back = False
                detail = (detail + "; " if detail else "") + \
                    f"rollback failed: {type(e).__name__}: {e}"
        return FaultResult(fault.name, injected, verified, rolled_back,
                           detail)
