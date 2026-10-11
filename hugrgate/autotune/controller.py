"""Optimization controller. Slice 451.

The controller is the spine of Campaign XIX. It owns:

- the :class:`ConfigStore`: the typed registry of tunable parameters
  (bounds, dtypes, defaults) with snapshot/restore and validated apply;
- the :class:`Tuner` protocol every optimizer plugs into;
- the :class:`Mode` lifecycle (offline / shadow / canary / applied)
  with a driver registry — the concrete drivers land in slices 466-468;
- the per-cycle pipeline: tuners propose, constraints validate, the
  mode driver disposes, and every step is journaled.

Deliberate non-goals: the controller does not *choose* objectives
(slice 452), does not *define* constraints (slice 453), and does not
enforce the full safety-limit policy (slice 472). It does enforce the
hard invariant that only registered, in-bounds, correctly-typed values
can ever be applied — that check lives here, not in the drivers.
"""

from __future__ import annotations

import enum
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from hugrgate.errors import (
    AutotuneError,
    ConstraintViolation,
    ParameterError,
)

__all__ = [
    "DEFAULT_MODES",
    "ConfigStore",
    "Disposition",
    "DriverResult",
    "Mode",
    "ModeDriver",
    "OptimizationController",
    "Proposal",
    "TunableParameter",
    "Tuner",
    "TuningContext",
    "TuningRun",
]


class Mode(str, enum.Enum):
    """Where a proposal goes after validation."""

    OFFLINE = "offline"  # record only; never touches live config (466)
    SHADOW = "shadow"  # propose + compare against live, no apply (467)
    CANARY = "canary"  # apply to a traffic fraction with guardrails (468)
    APPLIED = "applied"  # apply fleet-wide (requires canary evidence)


DEFAULT_MODES = tuple(m.value for m in Mode)


@dataclass(frozen=True)
class TunableParameter:
    """One knob the optimizer may turn.

    ``dtype`` is one of ``"float"``, ``"int"``, ``"bool"``, ``"str"``.
    Numeric dtypes require ``lo``/``hi``; ``"str"`` requires ``choices``.
    """

    name: str
    dtype: str
    default: Any
    description: str = ""
    owner: str = ""  # slice/component that owns this knob, e.g. "slice-454"
    lo: float | None = None
    hi: float | None = None
    choices: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ParameterError("parameter name must be a non-empty string",
                                 name=self.name)
        if self.dtype not in ("float", "int", "bool", "str"):
            raise ParameterError(f"unknown dtype {self.dtype!r}",
                                 name=self.name)
        if self.dtype in ("float", "int"):
            if self.lo is None or self.hi is None:
                raise ParameterError("numeric parameters require lo/hi",
                                     name=self.name)
            if self.lo > self.hi:
                raise ParameterError("lo must be <= hi", name=self.name)
        if self.dtype == "str":
            if not self.choices:
                raise ParameterError("str parameters require choices",
                                     name=self.name)
            if self.default not in self.choices:
                raise ParameterError("default must be one of choices",
                                     name=self.name)
        self._check_value(self.default, what="default")

    def _check_value(self, value: Any, what: str = "value") -> None:
        if self.dtype == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ParameterError(f"{what} must be numeric", name=self.name)
            if not (self.lo <= float(value) <= self.hi):  # type: ignore[operator]
                raise ParameterError(f"{what} out of bounds", name=self.name,
                                     value=value)
        elif self.dtype == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ParameterError(f"{what} must be an int", name=self.name)
            if not (self.lo <= value <= self.hi):  # type: ignore[operator]
                raise ParameterError(f"{what} out of bounds", name=self.name,
                                     value=value)
        elif self.dtype == "bool":
            if not isinstance(value, bool):
                raise ParameterError(f"{what} must be a bool", name=self.name)
        else:  # str
            if value not in self.choices:  # type: ignore[operator]
                raise ParameterError(f"{what} not in choices", name=self.name,
                                     value=value)

    def coerce(self, value: Any) -> Any:
        """Validate and normalize a candidate value."""
        self._check_value(value)
        if self.dtype == "float":
            return float(value)
        return value


class ConfigStore:
    """Thread-safe typed registry of tunable parameters.

    The store is the *single* enforcement point for parameter validity:
    :meth:`apply` rejects unknown names, wrong types, and out-of-bounds
    values with :class:`ParameterError` before anything is stored. Mode
    drivers and tuners may not bypass it.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._params: dict[str, TunableParameter] = {}
        self._values: dict[str, Any] = {}

    def register(self, param: TunableParameter) -> None:
        """Register a new tunable parameter at its default value."""
        with self._lock:
            if param.name in self._params:
                raise ParameterError("parameter already registered",
                                     name=param.name)
            self._params[param.name] = param
            self._values[param.name] = param.default

    def get(self, name: str) -> Any:
        with self._lock:
            if name not in self._params:
                raise ParameterError("unknown parameter", name=name)
            return self._values[name]

    def describe(self, name: str) -> TunableParameter:
        with self._lock:
            if name not in self._params:
                raise ParameterError("unknown parameter", name=name)
            return self._params[name]

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._params)

    def snapshot(self) -> dict[str, Any]:
        """A plain-dict copy of current values (JSON-serializable)."""
        with self._lock:
            return dict(self._values)

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        """Restore values from :meth:`snapshot`; validates everything."""
        with self._lock:
            coerced = {}
            for name, value in snapshot.items():
                param = self._params.get(name)
                if param is None:
                    raise ParameterError("unknown parameter", name=name)
                coerced[name] = param.coerce(value)
            self._values.update(coerced)

    def apply(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and apply changes; returns the applied values.

        Raises :class:`ParameterError` on the first invalid entry; the
        store is left untouched (all-or-nothing).
        """
        with self._lock:
            coerced: dict[str, Any] = {}
            for name, value in changes.items():
                param = self._params.get(name)
                if param is None:
                    raise ParameterError("unknown parameter", name=name)
                coerced[name] = param.coerce(value)
            self._values.update(coerced)
            return dict(coerced)

    def dry_run(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        """Validate ``changes`` and report what *would* be applied.

        Runs the exact same validation and coercion as :meth:`apply`
        (unknown names, wrong types, and out-of-bounds values raise
        :class:`ParameterError` and the store is left untouched), but
        never writes to the store. Returns a would-apply report with,
        for every parameter whose value would actually change, the
        ``old`` -> ``new`` values.
        """
        with self._lock:
            would_change: dict[str, dict[str, Any]] = {}
            for name, value in changes.items():
                param = self._params.get(name)
                if param is None:
                    raise ParameterError("unknown parameter", name=name)
                new = param.coerce(value)
                old = self._values[name]
                if new != old:
                    would_change[name] = {"old": old, "new": new}
            return {
                "would_change": would_change,
                "change_count": len(would_change),
                "mutated": False,
            }


@dataclass(frozen=True)
class Proposal:
    """One tuner's suggested change set, with its evidence."""

    proposal_id: str
    tuner: str
    changes: dict[str, Any]
    objective_id: str
    baseline: float
    estimate: float
    seed: int
    created_at: float = field(default_factory=time.time)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def delta(self) -> float:
        return self.estimate - self.baseline

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "tuner": self.tuner,
            "changes": dict(self.changes),
            "objective_id": self.objective_id,
            "baseline": self.baseline,
            "estimate": self.estimate,
            "delta": self.delta,
            "seed": self.seed,
            "created_at": self.created_at,
            "evidence": dict(self.evidence),
        }


@dataclass
class TuningContext:
    """What a tuner sees during a cycle. Immutable-ish view."""

    store: ConfigStore
    objectives: Mapping[str, Callable[[Mapping[str, Any]], float]]
    constraints: Sequence[Callable[[Mapping[str, Any]], None]]
    seed: int
    mode: Mode
    run_id: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def current(self) -> dict[str, Any]:
        return self.store.snapshot()

    def score(self, objective_id: str, values: Mapping[str, Any]) -> float:
        try:
            fn = self.objectives[objective_id]
        except KeyError as exc:
            raise AutotuneError("unknown objective",
                                objective=objective_id) from exc
        return float(fn(values))


class Tuner(Protocol):
    """Plug-in optimizer. Return ``None`` when no improvement found."""

    name: str

    def tune(self, ctx: TuningContext) -> Proposal | None:
        ...


class Disposition(str, enum.Enum):
    """What the mode driver did with a validated proposal."""

    RECORDED = "recorded"  # offline: journaled, nothing applied
    SHADOWED = "shadowed"  # shadow: compared, not applied
    CANARIED = "canaried"  # canary: applied to a fraction
    APPLIED = "applied"  # applied fleet-wide
    REJECTED = "rejected"  # blocked (constraint/safety/driver policy)
    SKIPPED = "skipped"  # tuner produced nothing or crashed


@dataclass(frozen=True)
class DriverResult:
    proposal_id: str
    disposition: Disposition
    detail: dict[str, Any] = field(default_factory=dict)


class ModeDriver(Protocol):
    """Disposes of validated proposals for one :class:`Mode`."""

    mode: Mode

    def handle(self, proposal: Proposal, ctx: TuningContext) -> DriverResult:
        ...


@dataclass
class TuningRun:
    """Journal entry for one controller cycle."""

    run_id: str
    mode: Mode
    seed: int
    started_at: float
    finished_at: float
    results: list[DriverResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode.value,
            "seed": self.seed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": [
                {
                    "proposal_id": r.proposal_id,
                    "disposition": r.disposition.value,
                    "detail": dict(r.detail),
                }
                for r in self.results
            ],
            "notes": list(self.notes),
        }


class _RecordingDriver:
    """Default driver: journal the proposal, change nothing.

    Used for every mode until slices 466-468 register the real drivers.
    """

    def __init__(self, mode: Mode, disposition: Disposition) -> None:
        self.mode = mode
        self._disposition = disposition

    def handle(self, proposal: Proposal, ctx: TuningContext) -> DriverResult:
        return DriverResult(
            proposal_id=proposal.proposal_id,
            disposition=self._disposition,
            detail={"driver": "recording-default",
                    "note": "real driver not yet registered"},
        )


class OptimizationController:
    """Runs tuning cycles: propose -> validate -> dispose -> journal.

    A crashed tuner is logged and skipped (:class:`TunerError` is
    recoverable); a constraint-violating proposal is rejected with
    :class:`ConstraintViolation` and the cycle continues. The tuning
    loop can therefore never take down the decision path — that is the
    load-bearing safety property of this campaign.
    """

    def __init__(self, store: ConfigStore | None = None) -> None:
        self.store = store or ConfigStore()
        self._tuners: dict[str, Tuner] = {}
        self._objectives: dict[str, Callable[[Mapping[str, Any]], float]] = {}
        self._constraints: list[Callable[[Mapping[str, Any]], None]] = []
        self._drivers: dict[Mode, ModeDriver] = {
            Mode.OFFLINE: _RecordingDriver(Mode.OFFLINE, Disposition.RECORDED),
            Mode.SHADOW: _RecordingDriver(Mode.SHADOW, Disposition.SHADOWED),
            Mode.CANARY: _RecordingDriver(Mode.CANARY, Disposition.CANARIED),
            Mode.APPLIED: _RecordingDriver(Mode.APPLIED, Disposition.APPLIED),
        }
        self._history: list[TuningRun] = []
        self._lock = threading.RLock()

    # -- registration -------------------------------------------------
    def register_tuner(self, tuner: Tuner) -> None:
        if not getattr(tuner, "name", None):
            raise AutotuneError("tuner must define a non-empty name")
        with self._lock:
            if tuner.name in self._tuners:
                raise AutotuneError("tuner already registered",
                                    tuner=tuner.name)
            self._tuners[tuner.name] = tuner

    def register_objective(self, objective_id: str,
                           fn: Callable[[Mapping[str, Any]], float]) -> None:
        if not objective_id:
            raise AutotuneError("objective id must be non-empty")
        with self._lock:
            self._objectives[objective_id] = fn

    def register_constraint(
        self, fn: Callable[[Mapping[str, Any]], None]
    ) -> None:
        """A constraint raises :class:`ConstraintViolation` when broken."""
        with self._lock:
            self._constraints.append(fn)

    def register_driver(self, driver: ModeDriver) -> None:
        with self._lock:
            self._drivers[driver.mode] = driver

    @property
    def tuners(self) -> list[str]:
        with self._lock:
            return sorted(self._tuners)

    @property
    def history(self) -> list[TuningRun]:
        with self._lock:
            return list(self._history)

    # -- the cycle ----------------------------------------------------
    def run_cycle(self, mode: Mode = Mode.OFFLINE, seed: int = 0,
                  data: Mapping[str, Any] | None = None) -> TuningRun:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        started = time.time()
        run = TuningRun(run_id=run_id, mode=mode, seed=seed,
                       started_at=started, finished_at=started)
        with self._lock:
            tuners = list(self._tuners.values())
            objectives = dict(self._objectives)
            constraints = list(self._constraints)
            driver = self._drivers[mode]
        ctx = TuningContext(store=self.store, objectives=objectives,
                            constraints=constraints, seed=seed, mode=mode,
                            run_id=run_id, data=dict(data or {}))
        for tuner in tuners:
            try:
                proposal = tuner.tune(ctx)
            except ConstraintViolation:
                # A tuner may self-report a constraint breach instead of
                # proposing; treat as a rejection, not a crash.
                run.results.append(DriverResult(
                    proposal_id="", disposition=Disposition.REJECTED,
                    detail={"tuner": tuner.name,
                            "reason": "constraint_violation"}))
                continue
            except Exception as exc:  # noqa: BLE001 - tuner isolation
                run.notes.append(f"tuner {tuner.name} failed: {exc!r}")
                run.results.append(DriverResult(
                    proposal_id="", disposition=Disposition.SKIPPED,
                    detail={"tuner": tuner.name, "error": repr(exc)}))
                continue
            if proposal is None:
                run.results.append(DriverResult(
                    proposal_id="", disposition=Disposition.SKIPPED,
                    detail={"tuner": tuner.name,
                            "reason": "no-improvement"}))
                continue
            # Hard invariant: only registered, in-bounds, correctly-typed
            # values may ever reach a driver. This is the single
            # enforcement point — drivers must not re-validate.
            for pname, pvalue in proposal.changes.items():
                self.store.describe(pname).coerce(pvalue)
            # Validate the proposal's changes before the driver sees them.
            try:
                candidate = dict(ctx.current())
                candidate.update(proposal.changes)
                for check in constraints:
                    check(candidate)
            except ConstraintViolation as exc:
                run.results.append(DriverResult(
                    proposal_id=proposal.proposal_id,
                    disposition=Disposition.REJECTED,
                    detail={"tuner": tuner.name, "reason": str(exc)}))
                continue
            result = driver.handle(proposal, ctx)
            run.results.append(result)
        run.finished_at = time.time()
        with self._lock:
            self._history.append(run)
        return run
