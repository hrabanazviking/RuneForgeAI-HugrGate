"""Routing fuzz tests. Slice 073.

A stdlib-only differential/robustness harness: seeded PRNGs generate
random registries (including *hostile* backends — raisers, liars,
abstainers, slowpokes), random specs, policies, options, planners, and
executors, then run real climbs checking hard invariants:

1. **No unexpected exception escapes** — only ``HugrGateError``
   (incl. ``Abstention``) may leave ``decide()``. A backend raising
   ``RuntimeError`` must become ``RUNG_ERROR``, never a crash.
2. **Result validity** — a returned result passes ``validate_result``
   and carries ``ladder_trace`` + ``routing_plan`` metadata.
3. **Audit integrity** — every entry has a known outcome string and a
   valid rung index; ``last_audit`` matches the returned trace.
4. **Determinism** — the same seed twice gives the same winner and
   probability (serial executors; thread scheduling makes parallel
   completion order nondeterministic by nature).

:func:`run_fuzz` returns a report dict; the pytest module asserts zero
violations across fixed seeds. This is a *harness*, not a one-off:
extend ``_BEHAVIORS``, ``_planner``, and ``_executor`` to cover new
components.
"""

from __future__ import annotations

import random
import time
from typing import Any

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import BackendError, BackendUnavailable, HugrGateError
from hugrgate.ladder import LadderRung
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.routing.architecture import (
    LadderRouterV2,
    RoutingOptions,
    RungPlanner,
    SerialPlanExecutor,
)
from hugrgate.routing.early_exit import EarlyExitExecutor
from hugrgate.routing.fallback import FallbackGraph, FallbackGraphExecutor
from hugrgate.routing.rungs import DynamicRungPlanner, RungBuilder
from hugrgate.routing.synthesis import LadderSynthesizer
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result

__all__ = [
    "KNOWN_OUTCOMES",
    "FuzzBackend",
    "run_fuzz",
]

KNOWN_OUTCOMES = {
    "accepted", "below_confidence", "skipped_unknown_backend",
    "skipped_unsupported", "skipped_privacy_blocked",
    "skipped_latency_budget", "backend_unavailable", "backend_error",
    "backend_abstained", "cancelled",
}

_BEHAVIORS = ("honest", "weak", "raiser", "unavailable", "abstainer",
              "liar_prob", "liar_dist", "nan_prob", "slow", "none_return")


class FuzzBackend(Backend):
    """A backend with seeded random (mis)behavior."""

    def __init__(self, name: str, rng: random.Random, remote: bool):
        self.name = name
        self._rng = rng
        self.is_remote = remote
        self.behavior = rng.choice(_BEHAVIORS)
        self.calls = 0

    def capabilities(self):
        caps: dict[str, Any] = {"spec_types": ["categorical"]}
        if self._rng.random() < 0.3:
            caps["accuracy"] = round(self._rng.uniform(0.5, 1.0), 2)
        return caps

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        b = self.behavior
        if b == "none_return":
            return None
        if b == "slow":
            time.sleep(self._rng.uniform(0.001, 0.005))
        if b == "raiser":
            raise [BackendError("x"), RuntimeError("y"),
                   ValueError("z")][self._rng.randrange(3)]
        if b == "unavailable":
            raise BackendUnavailable("gone")
        if b == "abstainer":
            from hugrgate.errors import Abstention
            raise Abstention("nope", reason="fuzz")
        prob = {"honest": 0.95, "weak": 0.4, "slow": 0.9,
                "liar_prob": 1.5, "liar_dist": 0.9,
                "nan_prob": float("nan")}[b]
        n = len(spec.options)
        if b == "liar_dist":
            dist = {o: 0.1 for o in spec.options}  # sums wrong
        else:
            rest = (1.0 - prob) / max(n - 1, 1) if prob == prob else 0.0
            dist = {o: (prob if o == "a" else rest) for o in spec.options}
        return DecisionResult(value="a", probability=prob,
                              distribution=dist, backend=self.name)

    def estimated_latency(self):
        return self._rng.uniform(1.0, 200.0)

    def estimated_cost(self):
        return round(self._rng.uniform(0.0, 0.5), 4)


def _random_policy(rng: random.Random, names: list[str]) -> DecisionPolicy:
    return DecisionPolicy(
        minimum_probability=round(rng.uniform(0.0, 0.95), 2),
        maximum_latency_ms=rng.choice(
            [None, round(rng.uniform(5.0, 500.0), 1)]),
        remote_inference=rng.random() < 0.5,
        allowed_backends=rng.choice(
            [None, rng.sample(names, rng.randint(1, len(names)))]),
        privacy_class=rng.choice(["standard", "strict"]),
        max_cost=rng.choice([None, round(rng.uniform(0.01, 1.0), 2)]),
    )


def _random_options(rng: random.Random) -> RoutingOptions:
    return RoutingOptions(
        qos=rng.choice(["best_effort", "standard", "priority",
                        "critical"]),
        hedge_delay_ms=round(rng.uniform(5.0, 50.0), 1),
        parallel_width=rng.randint(1, 4),
        fast_path_probability=round(rng.uniform(0.9, 0.999), 3),
        max_cost=rng.choice([None, round(rng.uniform(0.01, 0.5), 2)]),
    )


def _planner(rng: random.Random,
              registry) -> RungPlanner | None:
    return rng.choice([
        None,
        DynamicRungPlanner(registry),
        DynamicRungPlanner(registry, RungBuilder(order="latency")),
        LadderSynthesizer(registry),
    ])


def _executor(rng: random.Random):
    kind = rng.choice(["serial", "early_exit", "fallback"])
    if kind == "serial":
        return SerialPlanExecutor(), True
    if kind == "early_exit":
        return EarlyExitExecutor(), True
    graph = FallbackGraph()
    return FallbackGraphExecutor(graph), True
    # NOTE: parallel/hedged executors are exercised in their own slice
    # tests; fuzz determinism checks require serial scheduling.


def run_fuzz(seed: int, iterations: int = 100) -> dict[str, Any]:
    """Run seeded fuzz iterations; return the violation report."""
    violations: list[str] = []
    decided = abstained = 0

    for it in range(iterations):
        tag = f"seed={seed} it={it}"
        outcome = _one_iteration(seed, it)
        if outcome["error"] is not None:
            kind, detail = outcome["error"]
            if kind == "unexpected":
                violations.append(f"{tag}: unexpected {detail}")
            else:
                abstained += 1
            continue
        decided += 1
        violations.extend(_check_invariants(tag, seed, it, outcome))

    return {"seed": seed, "iterations": iterations, "decided": decided,
            "abstained": abstained, "violations": violations}


def _one_iteration(seed: int, it: int) -> dict[str, Any]:
    """One fully deterministic fuzz iteration.

    Every RNG derives from ``(seed, it)``, so re-running the same
    ``(seed, it)`` replays the identical registry, policy, and backend
    behaviors — the basis of the determinism invariant.
    """
    rng = random.Random(f"{seed}:{it}")
    n_backends = rng.randint(1, 5)
    names = [f"b{i}" for i in range(n_backends)]
    registry = BackendRegistry()
    for name in names:
        registry.register(FuzzBackend(
            name, random.Random(f"{seed}:{it}:{name}"),
            remote=rng.random() < 0.4))
    policy = _random_policy(rng, names)
    options = _random_options(rng)
    spec = DecisionSpec(type="categorical", options=["a", "b", "c"])
    planner = _planner(rng, registry)
    executor, deterministic = _executor(rng)
    rungs = [LadderRung(n, round(rng.uniform(0.0, 0.95), 2))
             for n in names]

    router = LadderRouterV2(registry, rungs=rungs,
                            planner=planner, executor=executor)
    try:
        result = router.decide({"k": "v"}, spec, policy, options=options)
    except HugrGateError as e:
        return {"error": ("expected", f"{type(e).__name__}: {e}"),
                "deterministic": deterministic}
    except Exception as e:  # noqa: BLE001 — the whole point of fuzzing
        return {"error": ("unexpected", f"{type(e).__name__}: {e}"),
                "deterministic": deterministic}
    return {"error": None, "router": router, "result": result,
            "spec": spec, "deterministic": deterministic}


def _check_invariants(tag: str, seed: int, it: int,
                      outcome: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    router = outcome["router"]
    result = outcome["result"]
    spec = outcome["spec"]

    # Invariant 2: result validity.
    try:
        validate_result(result, spec)
    except Exception as e:  # noqa: BLE001
        violations.append(f"{tag}: invalid result: {e}")
    md = result.metadata
    if "ladder_trace" not in md or "routing_plan" not in md:
        violations.append(f"{tag}: missing trace/plan metadata")

    # Invariant 3: audit integrity.
    trace = md.get("ladder_trace", [])
    for entry in trace:
        if entry["outcome"] not in KNOWN_OUTCOMES:
            violations.append(
                f"{tag}: unknown outcome {entry['outcome']!r}")
        if not isinstance(entry["rung_index"], int) \
                or entry["rung_index"] < 0:
            violations.append(f"{tag}: bad rung_index {entry!r}")
    last = router.last_audit
    if len(last) != len(trace):
        violations.append(
            f"{tag}: last_audit len {len(last)} != trace {len(trace)}")

    # Invariant 4: determinism — replay the identical (seed, it).
    if outcome["deterministic"]:
        rerun = _one_iteration(seed, it)
        if rerun["error"] is not None:
            violations.append(
                f"{tag}: rerun diverged: {rerun['error'][1]}")
        elif (rerun["result"].backend, rerun["result"].probability) != (
                result.backend, result.probability):
            violations.append(f"{tag}: nondeterministic rerun")
    return violations
