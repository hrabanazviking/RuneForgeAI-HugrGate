"""Ready-made chaos experiments. Slices 266-267.

The framework (:mod:`hugrgate.chaos.framework`) is the experiment
*discipline*; this module is the *library* of standard experiments
built from the fault injectors:

- :func:`partial_service_failure_experiment` (266) — crash a subset
  of a service's backends and verify the survivors keep serving;
- :func:`dependency_failure_matrix` (267) — run a matrix of
  dependency-outage scenarios and report which the system survives.

:class:`ServiceUnderTest` is the harness: a :class:`FallbackChain`
over named backends, some wrapped in :class:`FaultyBackend` so the
experiment can break and heal them.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from unittest import mock

from hugrgate.backend import Backend
from hugrgate.chaos.backend_faults import CRASH, FaultSpec, FaultyBackend
from hugrgate.chaos.framework import (
    BlastRadius,
    ChaosExperiment,
    ExperimentRunner,
    Fault,
    ProbeOutcome,
    SteadyStateProbe,
)
from hugrgate.errors import Abstention, BackendError, SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result

__all__ = [
    "CHAOS_LAB",
    "DependencyMatrix",
    "DependencyScenario",
    "ServiceUnderTest",
    "builtin_dependency_matrix",
    "dependency_failure_matrix",
    "partial_service_failure_experiment",
    "run_experiment_on_lab",
]

#: The only blast-radius target the built-in experiments may touch.
CHAOS_LAB = "chaos-lab"


class ServiceUnderTest:
    """A fallback chain whose named backends can be crashed and healed."""

    def __init__(self, backends: Sequence[Backend],
                 breakable: Collection[str],
                 policy: DecisionPolicy | None = None,
                 safe_default: Any = None):
        if not backends:
            raise SpecError("ServiceUnderTest needs at least one backend")
        names = [b.name for b in backends]
        if len(set(names)) != len(names):
            raise SpecError(f"backend names must be unique, got {names}")
        unknown = set(breakable) - set(names)
        if unknown:
            raise SpecError(
                f"breakable names not in backends: {sorted(unknown)}")
        self.policy = policy or DecisionPolicy()
        self._faulty: dict[str, FaultyBackend] = {}
        wrapped: list[Backend] = []
        for backend in backends:
            if backend.name in breakable:
                faulty = FaultyBackend(backend)
                self._faulty[backend.name] = faulty
                wrapped.append(faulty)
            else:
                wrapped.append(backend)
        self.chain = FallbackChain(wrapped, policy=self.policy,
                                    safe_default=safe_default)
        self._names = names

    @property
    def names(self) -> list[str]:
        return list(self._names)

    @property
    def breakable(self) -> list[str]:
        return sorted(self._faulty)

    def inject_crash(self, name: str) -> None:
        try:
            faulty = self._faulty[name]
        except KeyError:
            raise SpecError(
                f"backend {name!r} is not breakable") from None
        faulty.arm(FaultSpec(mode=CRASH, rate=1.0, seed=0))

    def recover(self, name: str) -> None:
        try:
            faulty = self._faulty[name]
        except KeyError:
            raise SpecError(
                f"backend {name!r} is not breakable") from None
        faulty.disarm_all()

    def decide(self, state: Mapping[str, Any],
               spec: DecisionSpec) -> DecisionResult:
        """Decide through the chain, mirroring the core decision path
        (:meth:`hugrgate.core.HugrGate.decide`): result validation and
        the policy gate apply, so a below-threshold result abstains
        instead of being served."""
        result = self.chain.evaluate(state, spec)
        validate_result(result, spec)
        if self.policy.evaluate(result) == "abstain":
            raise Abstention(
                f"probability {result.probability:.3f} below threshold "
                f"{self.policy.minimum_probability:.3f}",
                reason="below_threshold", backend="service-under-test")
        result.accepted = True
        return result

    def crashed_names(self) -> list[str]:
        """Backends currently crashed (fault armed)."""
        return sorted(n for n, f in self._faulty.items()
                      if f.armed_modes())

    def is_healthy(self) -> bool:
        """No backend is currently crashed."""
        return not self.crashed_names()


def _serves_probe(service: ServiceUnderTest, state: Mapping[str, Any],
                  spec: DecisionSpec) -> SteadyStateProbe:
    def check() -> ProbeOutcome:
        try:
            result = service.decide(dict(state), spec)
        except Exception as e:  # noqa: BLE001 - probe failure is data
            return ProbeOutcome(False, f"{type(e).__name__}: {e}")
        if not result.accepted:
            return ProbeOutcome(False, "result not accepted")
        return ProbeOutcome(True, f"served by "
                                 f"{result.metadata.get('decided_by')}")
    return SteadyStateProbe("service-serves", check)


def _policy_intact_probe(policy: DecisionPolicy) -> SteadyStateProbe:
    fingerprint = (policy.minimum_probability, policy.remote_inference,
                   policy.fallback_behavior)

    def check() -> ProbeOutcome:
        current = (policy.minimum_probability, policy.remote_inference,
                   policy.fallback_behavior)
        if current != fingerprint:
            return ProbeOutcome(False,
                                f"policy mutated: {fingerprint} -> {current}")
        return ProbeOutcome(True, "policy unchanged")
    return SteadyStateProbe("policy-intact", check)


def partial_service_failure_experiment(
        service: ServiceUnderTest,
        failing_names: Collection[str],
        state: Mapping[str, Any],
        spec: DecisionSpec,
        *,
        name: str = "partial-service-failure",
        seed: int | None = 266,
        simultaneous: bool = False) -> ChaosExperiment:
    """Build the partial-service-failure experiment.

    Hypothesis (``simultaneous=False``): "when ``failing_names`` crash
    one at a time, the service keeps serving via the survivors and
    policy is not weakened." Each failing backend becomes one fault:
    inject crashes it, verify asserts it is crashed *and* the service
    still serves an accepted result, rollback heals it.

    Hypothesis (``simultaneous=True``): "when ``failing_names`` all
    crash at once, the service fails *cleanly* — it abstains instead
    of serving garbage or hanging." One fault crashes everything;
    verify asserts ``decide`` raises instead of serving.

    Steady-state probes assert the service served *before* the first
    fault and serves *after* the last rollback, and that policy is
    intact throughout. A falsified hypothesis is reported as a
    failure, never passed quietly.
    """
    failing = list(failing_names)
    if not failing:
        raise SpecError("failing_names must be non-empty")
    unknown = set(failing) - set(service.breakable)
    if unknown:
        raise SpecError(
            f"cannot fail unbreakable backends: {sorted(unknown)}")

    if simultaneous:
        faults = (_simultaneous_fault(service, failing, state, spec),)
        hypothesis = (f"the service fails cleanly when {sorted(failing)} "
                      f"all fail at once")
    else:
        faults = tuple(_single_fault(service, victim, state, spec)
                       for victim in failing)
        hypothesis = (f"the service keeps serving when "
                      f"{sorted(failing)} fail")

    return ChaosExperiment(
        name=name,
        hypothesis=hypothesis,
        faults=faults,
        probes=(_serves_probe(service, state, spec),
                _policy_intact_probe(service.policy)),
        blast_radius=BlastRadius(allowed_targets=frozenset({CHAOS_LAB})),
        seed=seed,
    )


def _single_fault(service: ServiceUnderTest, victim: str,
                  state: Mapping[str, Any],
                  spec: DecisionSpec) -> Fault:
    def inject(ctx: dict[str, Any]) -> None:
        service.inject_crash(victim)

    def verify(ctx: dict[str, Any]) -> None:
        # The victim must be crashed *right now* — otherwise the
        # verification is vacuous.
        if victim not in service.crashed_names():
            raise AssertionError(
                f"fault {victim!r} is not armed during verification")
        result = service.decide(dict(state), spec)
        if not result.accepted:
            raise AssertionError("service did not serve an "
                                 "accepted result")

    def rollback(ctx: dict[str, Any]) -> None:
        service.recover(victim)

    return Fault(
        name=f"crash-{victim}",
        description=f"crash backend {victim!r}; survivors must serve",
        inject=inject,
        verify=verify,
        rollback=rollback,
    )


def _simultaneous_fault(service: ServiceUnderTest, victims: list[str],
                        state: Mapping[str, Any],
                        spec: DecisionSpec) -> Fault:
    def inject(ctx: dict[str, Any]) -> None:
        for victim in victims:
            service.inject_crash(victim)

    def verify(ctx: dict[str, Any]) -> None:
        crashed = service.crashed_names()
        missing = [v for v in victims if v not in crashed]
        if missing:
            raise AssertionError(
                f"victims not crashed during verification: {missing}")
        try:
            result = service.decide(dict(state), spec)
        except (Abstention, SpecError):
            return  # clean failure: the hypothesis holds
        raise AssertionError(
            f"service served {result.value!r} with every backend "
            f"crashed — expected a clean abstention")

    def rollback(ctx: dict[str, Any]) -> None:
        for victim in victims:
            service.recover(victim)

    return Fault(
        name="crash-all",
        description=(f"crash {sorted(victims)} at once; the service "
                     f"must fail cleanly"),
        inject=inject,
        verify=verify,
        rollback=rollback,
    )


def run_experiment_on_lab(experiment: ChaosExperiment) -> dict[str, Any]:
    """Run an experiment against the chaos-lab target; return the
    JSON-serializable report."""
    report = ExperimentRunner().run(experiment, CHAOS_LAB)
    return report.to_dict()


# --- dependency failure matrix (slice 267) -----------------------------------------------

@dataclass(frozen=True)
class DependencyScenario:
    """One dependency outage: how to break it, how to check the
    system degraded gracefully.

    ``break_it`` puts the dependency into its failed state and
    returns a ``restore()`` callable; ``check`` raises
    ``AssertionError`` when the degradation was *not* graceful
    (wrong exception type, leaked ``ImportError``, hung, or
    corrupted state). ``restore`` runs even when ``check`` raises.
    """

    name: str
    description: str
    break_it: Callable[[], Callable[[], None]]
    check: Callable[[], None]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("dependency scenario name must be non-empty")
        if not self.description.strip():
            raise SpecError(
                "dependency scenario description must be non-empty")


@dataclass
class _ScenarioOutcome:
    name: str
    survived: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "survived": self.survived,
                "detail": self.detail}


class DependencyMatrix:
    """A matrix of dependency-failure scenarios with a report.

    Like the experiment runner, ``run_all`` never aborts: a raising
    scenario is a recorded non-survival, and every scenario's
    ``restore`` runs regardless.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._scenarios: dict[str, DependencyScenario] = {}

    def add(self, scenario: DependencyScenario) -> DependencyMatrix:
        if not isinstance(scenario, DependencyScenario):
            raise SpecError(
                "can only add DependencyScenario, got "
                f"{type(scenario).__name__}")
        with self._lock:
            if scenario.name in self._scenarios:
                raise SpecError(
                    f"duplicate dependency scenario {scenario.name!r}")
            self._scenarios[scenario.name] = scenario
        return self

    def scenarios(self) -> list[str]:
        with self._lock:
            return sorted(self._scenarios)

    def run_all(self) -> dict[str, Any]:
        outcomes: list[_ScenarioOutcome] = []
        with self._lock:
            scenarios = [self._scenarios[n]
                         for n in sorted(self._scenarios)]
        for scenario in scenarios:
            restore = None
            try:
                restore = scenario.break_it()
            except Exception as e:  # noqa: BLE001 - recorded per scenario
                outcomes.append(_ScenarioOutcome(
                    scenario.name, False,
                    f"break_it failed: {type(e).__name__}: {e}"))
                continue
            try:
                try:
                    scenario.check()
                except Exception as e:  # noqa: BLE001 - recorded
                    outcomes.append(_ScenarioOutcome(
                        scenario.name, False,
                        f"did not degrade gracefully: "
                        f"{type(e).__name__}: {e}"))
                else:
                    outcomes.append(_ScenarioOutcome(scenario.name, True))
            finally:
                if restore is not None:
                    try:
                        restore()
                    except Exception as e:  # noqa: BLE001 - recorded
                        outcomes[-1].detail += (
                            f"; restore failed: {type(e).__name__}: {e}")
                        outcomes[-1].survived = False
        failed = [o.name for o in outcomes if not o.survived]
        return {"scenarios": len(outcomes),
                "survived": len(outcomes) - len(failed),
                "failed": failed,
                "results": [o.to_dict() for o in outcomes],
                "all_survived": not failed and bool(outcomes)}


def _patch_module_attr(module_name: str, attr: str,
                       value: Any) -> Callable[[], None]:
    """Break a module attribute; return the restore callable."""
    import importlib
    module = importlib.import_module(module_name)
    patcher = mock.patch.object(module, attr, value)
    patcher.start()
    return patcher.stop


def _expect_backend_error_hint(call: Callable[[], None],
                               hint: str = "install") -> None:
    """Assert ``call`` raises BackendError with a helpful message —
    the graceful shape of a missing optional dependency."""
    try:
        call()
    except BackendError as e:
        if hint not in str(e).lower():
            raise AssertionError(
                f"missing-dependency error lacks an install hint: {e}"
            ) from e
        return
    except Exception as e:
        raise AssertionError(
            f"missing dependency leaked {type(e).__name__}: {e} "
            f"(expected BackendError)") from e
    raise AssertionError("missing dependency did not raise at all")


def builtin_dependency_matrix() -> DependencyMatrix:
    """The shipped matrix: optional-dependency outages.

    Each scenario simulates an absent optional dependency and
    asserts the failure surfaces as a helpful ``BackendError``
    (taxonomy, recoverable, with an install hint) — never a leaked
    ``ImportError`` or ``AttributeError``.
    """
    matrix = DependencyMatrix()

    def break_numpy():
        return _patch_module_attr(
            "hugrgate.backends.logreg", "np", None)

    def check_numpy():
        from hugrgate.backends.logreg import LogisticRegressionBackend
        from hugrgate.features import NumericEncoder, Pipeline
        backend = LogisticRegressionBackend(
            model_name="chaos-probe",
            feature_pipeline=Pipeline([NumericEncoder(["x"])]))
        _expect_backend_error_hint(
            lambda: backend.train([({"x": 1}, "a"), ({"x": 2}, "b")]))

    matrix.add(DependencyScenario(
        "ml-numpy-missing",
        "numpy absent: sklearn backend train() must raise BackendError "
        "with an install hint",
        break_numpy, check_numpy))

    def break_sklearn():
        return _patch_module_attr(
            "hugrgate.backends.logreg", "LogisticRegression", None)

    def check_sklearn():
        from hugrgate.backends.logreg import LogisticRegressionBackend
        from hugrgate.features import NumericEncoder, Pipeline
        backend = LogisticRegressionBackend(
            model_name="chaos-probe",
            feature_pipeline=Pipeline([NumericEncoder(["x"])]))
        _expect_backend_error_hint(
            lambda: backend.train([({"x": 1}, "a"), ({"x": 2}, "b")]))

    matrix.add(DependencyScenario(
        "ml-sklearn-missing",
        "scikit-learn absent: sklearn backend train() must raise "
        "BackendError with an install hint",
        break_sklearn, check_sklearn))

    def break_embedding_numpy():
        return _patch_module_attr(
            "hugrgate.backends.embedding", "np", None)

    def check_embedding_numpy():
        from hugrgate.backends.embedding import PrototypeBackend
        _expect_backend_error_hint(lambda: PrototypeBackend())

    matrix.add(DependencyScenario(
        "embedding-numpy-missing",
        "numpy absent: PrototypeBackend() must raise BackendError "
        "with an install hint",
        break_embedding_numpy, check_embedding_numpy))

    return matrix


def dependency_failure_matrix() -> dict[str, Any]:
    """Run the built-in dependency failure matrix; return the
    JSON-serializable report."""
    import json
    report = builtin_dependency_matrix().run_all()
    json.dumps(report)  # contract: always serializable
    return report
