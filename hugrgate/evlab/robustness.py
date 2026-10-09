"""Robustness evaluation — quality under perturbation. Slice 367.

A backend's clean-dataset accuracy is a fair-weather number.  This
module stresses it with seeded, reproducible perturbations applied to
the *inputs* before evaluation:

- :class:`LabelNoise` — flips each expected label with probability
  ``p`` (categorical options / binary booleans);
- :class:`StateDropout` — drops each state key independently with
  probability ``p`` (at least one key is always kept: this measures
  graceful degradation, not crash behavior — crashes belong to the
  chaos campaign).

:func:`robustness_evaluate` scores every backend on the clean baseline
plus each perturbation and reports per-perturbation accuracy,
relative retention (perturbed / baseline), and the worst-case
``robustness_score`` (min retention).  All randomness flows through
``random.Random(seed)`` — the same seed replays the same storm.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate import bench as _bench
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "LabelNoise",
    "Perturbation",
    "RobustnessReport",
    "StateDropout",
    "robustness_evaluate",
]


class Perturbation(ABC):
    """A seeded transformation of evaluation items."""

    name: str = "perturbation"

    @abstractmethod
    def apply(
        self,
        items: list[dict[str, Any]],
        spec: DecisionSpec,
        rng: random.Random,
    ) -> list[dict[str, Any]]:
        """Return perturbed copies; never mutate the inputs."""


def _check_p(p: float, name: str) -> float:
    if not 0.0 <= p <= 1.0:
        raise EvalError(f"{name} p must be in [0, 1], got {p}")
    return p


class LabelNoise(Perturbation):
    """Flip each expected label with probability ``p``."""

    def __init__(self, p: float) -> None:
        self.p = _check_p(p, "LabelNoise")
        self.name = f"label_noise(p={self.p})"

    def apply(self, items, spec, rng):
        if spec.type == "categorical":
            options = list(spec.options or [])
            if len(options) < 2:
                raise EvalError(
                    "LabelNoise needs 2+ categorical options")
        elif spec.type == "binary":
            options = None
        else:
            raise EvalError(
                f"LabelNoise supports categorical/binary specs, got "
                f"{spec.type!r}")
        perturbed = []
        for item in items:
            row = dict(item)
            expected = row.get("expected")
            if expected is not None and rng.random() < self.p:
                if options is None:
                    row["expected"] = not expected
                else:
                    choices = [o for o in options if o != expected]
                    row["expected"] = (rng.choice(choices)
                                       if choices else expected)
            perturbed.append(row)
        return perturbed


class StateDropout(Perturbation):
    """Drop each state key independently with probability ``p``.

    At least one key survives per item (documented): the stress is
    missing *features*, not empty states.
    """

    def __init__(self, p: float) -> None:
        self.p = _check_p(p, "StateDropout")
        self.name = f"state_dropout(p={self.p})"

    def apply(self, items, spec, rng):
        perturbed = []
        for item in items:
            row = dict(item)
            state = item.get("state")
            if isinstance(state, Mapping) and state:
                kept = {k: v for k, v in state.items()
                        if rng.random() >= self.p}
                if not kept:
                    keep_key = rng.choice(sorted(state, key=repr))
                    kept = {keep_key: state[keep_key]}
                row["state"] = kept
            perturbed.append(row)
        return perturbed


def _evaluate_accuracy(
    gate: HugrGate,
    dataset: Mapping[str, Any],
    items: list[dict[str, Any]],
    backend: str,
    policy: DecisionPolicy,
) -> tuple[float | None, int]:
    spec = DecisionSpec.from_dict(dataset["spec"])
    pairs: list[tuple[Any, DecisionResult]] = []
    for item in items:
        try:
            result = gate.decide(dict(item["state"]), spec, policy,
                                 backend_name=backend)
        except Abstention:
            continue
        pairs.append((item.get("expected"), result))
    return _bench.accuracy(pairs), len(pairs)


@dataclass
class RobustnessReport:
    """Per-backend robustness results (slice 367)."""

    backends: dict[str, dict[str, Any]]
    perturbations: list[str]
    n_items: int
    seed: int

    def most_robust(self) -> tuple[str | None, float | None]:
        """(backend, robustness_score) with the best worst case."""
        scored = [
            (b, info["robustness_score"])
            for b, info in self.backends.items()
            if isinstance(info["robustness_score"], (int, float))
        ]
        if not scored:
            return None, None
        return max(scored, key=lambda kv: kv[1])

    def fragile(
        self, threshold: float = 0.8
    ) -> list[tuple[str, float]]:
        """Backends whose worst-case retention falls below ``threshold``."""
        if not 0.0 <= threshold <= 1.0:
            raise EvalError(
                f"threshold must be in [0, 1], got {threshold}")
        return sorted(
            (b, info["robustness_score"])
            for b, info in self.backends.items()
            if isinstance(info["robustness_score"], (int, float))
            and info["robustness_score"] < threshold
        )

    def _backend(self, backend: str) -> dict[str, Any]:
        try:
            return self.backends[backend]
        except KeyError:
            raise EvalError(f"unknown backend {backend!r}") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info)
                         for b, info in self.backends.items()},
            "perturbations": list(self.perturbations),
            "n_items": self.n_items,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RobustnessReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            perturbations=list(data["perturbations"]),
            n_items=data["n_items"],
            seed=data["seed"],
        )


def robustness_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    perturbations: Sequence[Perturbation] | None = None,
    seed: int = 0,
    policy: DecisionPolicy | None = None,
    max_items: int | None = None,
) -> RobustnessReport:
    """Score backends on the clean baseline + each perturbation."""
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = [dict(i) for i in dataset.get("items", [])]
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("robustness evaluation needs at least one item")
    names = list(backends) if backends is not None \
        else [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise EvalError("no backends available for this dataset's spec")
    perturbations = list(perturbations) if perturbations is not None \
        else [LabelNoise(0.1), StateDropout(0.3)]

    results: dict[str, dict[str, Any]] = {}
    for backend in names:
        baseline, n = _evaluate_accuracy(gate, dataset, items, backend,
                                         policy)
        per_pert: dict[str, dict[str, Any]] = {}
        for pert in perturbations:
            rng = random.Random(seed)
            perturbed = pert.apply(items, spec, rng)
            acc, pn = _evaluate_accuracy(gate, dataset, perturbed,
                                         backend, policy)
            retention = (
                (acc / baseline)
                if acc is not None and baseline not in (None, 0)
                else None
            )
            per_pert[pert.name] = {
                "accuracy": acc,
                "n_decided": pn,
                "retention": retention,
            }
        retentions = [d["retention"] for d in per_pert.values()
                      if d["retention"] is not None]
        results[backend] = {
            "baseline_accuracy": baseline,
            "n_decided": n,
            "perturbations": per_pert,
            "robustness_score": min(retentions) if retentions else None,
            "mean_retention": (
                sum(retentions) / len(retentions) if retentions else None
            ),
        }
    return RobustnessReport(
        backends=results,
        perturbations=[p.name for p in perturbations],
        n_items=len(items),
        seed=seed,
    )
