"""Privacy-aware evaluation — the utility cost of privacy. Slice 366.

Three honest instruments, each labeled with its limits:

1. **PII pre-screen** (:func:`scan_dataset_pii`): runs
   :class:`hugrgate.privacy_pii.RegexPIIDetector` over item states
   *before* any evaluation.  Findings produce a :class:`PIIReport`
   with ``requires_restricted=True``; :meth:`PIIReport.assert_privacy`
   raises :class:`EvalError` telling the operator to flag the dataset
   ``sensitivity="restricted"`` — which the lab's
   :class:`~hugrgate.evlab.api.Experiment` gate then enforces against
   the policy's privacy class.
2. **Privacy-utility curves** (:func:`privacy_utility_curve`):
   randomized-response simulation — each decision is flipped to a
   random alternative with probability ``q(epsilon) =
   1/(1+e^epsilon)``.  This traces the *shape* of the privacy/utility
   tradeoff.  It is **not** a differential-privacy guarantee: no
   budget is tracked, no mechanism is certified, and every report
   carries that disclaimer.
3. **Flip-probability math** (:func:`randomized_response_q`): the
   closed form, validated.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.bench import accuracy as _bench_accuracy
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_pii import RegexPIIDetector
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "PIIReport",
    "PrivacyUtilityCurve",
    "PrivacyUtilityPoint",
    "privacy_utility_curve",
    "randomized_response_q",
    "scan_dataset_pii",
]

#: Carried on every privacy-utility artifact.
NOT_A_GUARANTEE = (
    "Simulation of the privacy/utility tradeoff shape via randomized "
    "response. Not a differential-privacy guarantee: no privacy budget "
    "is tracked and no mechanism is certified."
)


def randomized_response_q(epsilon: float) -> float:
    """Flip probability for randomized response at ``epsilon``.

    ``q = 1/(1+e^epsilon)``: epsilon → ∞ keeps every answer (q → 0);
    epsilon = 0 flips a coin (q = 0.5).
    """
    if math.isnan(epsilon) or epsilon < 0:
        raise EvalError(
            f"epsilon must be >= 0 (or inf), got {epsilon}"
        )
    if math.isinf(epsilon):
        return 0.0
    return 1.0 / (1.0 + math.exp(epsilon))


@dataclass
class PIIReport:
    """Outcome of a pre-evaluation PII scan (slice 366)."""

    dataset_name: str
    findings_by_kind: dict[str, int]
    items_scanned: int
    items_with_pii: int

    @property
    def total_findings(self) -> int:
        return sum(self.findings_by_kind.values())

    @property
    def requires_restricted(self) -> bool:
        """True when any PII was found: flag the dataset restricted."""
        return self.total_findings > 0

    def assert_privacy(self) -> None:
        """Raise unless the dataset may run under a standard policy."""
        if self.requires_restricted:
            kinds = ", ".join(
                f"{k} x{v}" for k, v in sorted(self.findings_by_kind.items())
            )
            raise EvalError(
                f"dataset {self.dataset_name!r} contains PII ({kinds}); "
                'flag it sensitivity="restricted" (or contains_pii=true) '
                "and re-run under a sensitive/strict privacy_class",
                pii_kinds=sorted(self.findings_by_kind),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "findings_by_kind": dict(self.findings_by_kind),
            "items_scanned": self.items_scanned,
            "items_with_pii": self.items_with_pii,
            "requires_restricted": self.requires_restricted,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PIIReport:
        return cls(
            dataset_name=data["dataset_name"],
            findings_by_kind=dict(data["findings_by_kind"]),
            items_scanned=data["items_scanned"],
            items_with_pii=data["items_with_pii"],
        )


def scan_dataset_pii(
    dataset: Mapping[str, Any],
    kinds: Sequence[str] | None = None,
    max_items: int | None = None,
) -> PIIReport:
    """Scan item states for PII; return a :class:`PIIReport`.

    Only the ``state`` mapping is scanned (labels are the operator's
    own).  Previews are counts by kind — raw PII never lands in the
    report.
    """
    detector = RegexPIIDetector(
        list(kinds) if kinds is not None else None)
    items = list(dataset.get("items", []))
    if max_items is not None:
        if max_items < 1:
            raise EvalError(f"max_items must be >= 1, got {max_items}")
        items = items[:max_items]
    by_kind: dict[str, int] = {}
    items_with_pii = 0
    for item in items:
        state = item.get("state")
        if not isinstance(state, Mapping):
            continue
        findings = detector.scan_state(state)
        if findings:
            items_with_pii += 1
            for finding in findings:
                by_kind[finding.kind] = by_kind.get(finding.kind, 0) + 1
    return PIIReport(
        dataset_name=str(dataset.get("name", "unnamed")),
        findings_by_kind=by_kind,
        items_scanned=len(items),
        items_with_pii=items_with_pii,
    )


@dataclass
class PrivacyUtilityPoint:
    """One epsilon on the privacy-utility curve."""

    epsilon: float
    flip_q: float
    accuracy: float | None
    n: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "epsilon": self.epsilon,
            "flip_q": self.flip_q,
            "accuracy": self.accuracy,
            "n": self.n,
        }


@dataclass
class PrivacyUtilityCurve:
    """Accuracy vs epsilon under randomized response (slice 366)."""

    backend: str
    baseline_accuracy: float | None
    points: list[PrivacyUtilityPoint]
    disclaimer: str = NOT_A_GUARANTEE

    def epsilon_for_accuracy(self, target: float) -> float | None:
        """Smallest epsilon whose accuracy reaches ``target``."""
        if not 0.0 <= target <= 1.0:
            raise EvalError(
                f"target accuracy must be in [0, 1], got {target}"
            )
        feasible = [
            pt.epsilon for pt in self.points
            if pt.accuracy is not None and pt.accuracy >= target
        ]
        return min(feasible) if feasible else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "baseline_accuracy": self.baseline_accuracy,
            "points": [pt.to_dict() for pt in self.points],
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PrivacyUtilityCurve:
        return cls(
            backend=data["backend"],
            baseline_accuracy=data["baseline_accuracy"],
            points=[PrivacyUtilityPoint(**pt) for pt in data["points"]],
            disclaimer=data.get("disclaimer", NOT_A_GUARANTEE),
        )


def privacy_utility_curve(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backend: str,
    epsilons: Sequence[float],
    seed: int = 0,
    policy: DecisionPolicy | None = None,
    max_items: int | None = None,
) -> PrivacyUtilityCurve:
    """Trace accuracy vs epsilon via randomized-response simulation."""
    if not epsilons:
        raise EvalError("need at least one epsilon")
    for eps in epsilons:
        randomized_response_q(eps)  # validates
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("privacy-utility curve needs at least one item")

    pairs: list[tuple[Any, DecisionResult]] = []
    for item in items:
        expected = item.get("expected")
        try:
            result = gate.decide(dict(item["state"]), spec, policy,
                                 backend_name=backend)
        except Abstention:
            continue
        pairs.append((expected, result))
    if not pairs:
        raise EvalError(
            f"backend {backend!r} produced no scored decisions"
        )
    baseline = _bench_accuracy(pairs)
    try:
        options = list(spec.value_space())
    except Exception:  # noqa: BLE001 - fall back to observed values
        options = sorted({r.value for _, r in pairs
                          if r.value is not None})

    rng = random.Random(seed)
    points: list[PrivacyUtilityPoint] = []
    for eps in sorted(epsilons):
        q = randomized_response_q(eps)
        noisy: list[tuple[Any, Any]] = []
        for expected, result in pairs:
            predicted = result.value
            if rng.random() < q:
                alternatives = [o for o in options if o != predicted]
                if alternatives:
                    predicted = rng.choice(alternatives)
            noisy.append((expected, predicted))
        scored = [(e, p) for e, p in noisy if e is not None]
        if isinstance(pairs[0][0], list):
            hits = sum(1 for e, p in scored
                       if set(p or []) == set(e))
        else:
            hits = sum(1 for e, p in scored if p == e)
        accuracy = hits / len(scored) if scored else None
        points.append(PrivacyUtilityPoint(
            epsilon=eps, flip_q=q, accuracy=accuracy, n=len(scored)))
    return PrivacyUtilityCurve(backend=backend,
                               baseline_accuracy=baseline,
                               points=points)
