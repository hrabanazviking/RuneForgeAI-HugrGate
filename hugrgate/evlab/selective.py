"""Selective-risk evaluation — risk-coverage curves per backend. Slice 362.

A backend that *knows when it is wrong* is safer than one that is
merely accurate: selective prediction keeps the most confident
decisions and abstains on the rest.  This module scores that ability:

- :func:`risk_coverage_curve` — pure-Python RC curve from per-item
  ``(correct, confidence)``: risk (mean 0/1 loss) vs coverage as the
  confidence threshold sweeps down.  (The numpy sibling lives in
  :mod:`hugrgate.calibration.risk_coverage`; this is the base-install
  lab version.)
- :func:`aurc` / :func:`oracle_aurc` — area under the curve; the
  oracle (sorted by true loss) bounds what confidence ranking can
  achieve, so ``excess = aurc - oracle`` measures ranking quality.
- :func:`selective_evaluate` — lab integration: evaluates backends
  once, builds a :class:`SelectiveReport` per backend, and anchors
  the gate's *own* abstention threshold
  (``policy.minimum_probability``) on the curve — is the configured
  threshold sitting at a sensible point, or is it leaving coverage
  (or safety) on the table?
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "SelectivePoint",
    "SelectiveReport",
    "aurc",
    "coverage_at_risk",
    "oracle_aurc",
    "risk_at_coverage",
    "risk_coverage_curve",
    "selective_evaluate",
]


@dataclass
class SelectivePoint:
    """One threshold on the risk-coverage curve."""

    threshold: float
    coverage: float
    risk: float
    accuracy: float
    n: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "coverage": self.coverage,
            "risk": self.risk,
            "accuracy": self.accuracy,
            "n": self.n,
        }


def _check_inputs(correct: Sequence[int],
                  confidences: Sequence[float]) -> tuple[list[int], list[float]]:
    y = [int(v) for v in correct]
    p = [float(v) for v in confidences]
    if len(y) != len(p):
        raise EvalError(
            f"correct/confidences length mismatch: {len(y)} vs {len(p)}"
        )
    if not y:
        raise EvalError("risk-coverage curve needs at least one item")
    for flag in y:
        if flag not in (0, 1):
            raise EvalError(f"correct flags must be 0/1, got {flag!r}")
    for conf in p:
        if not 0.0 <= conf <= 1.0:
            raise EvalError(f"confidence out of [0, 1]: {conf!r}")
    return y, p


def risk_coverage_curve(
    correct: Sequence[int],
    confidences: Sequence[float],
    n_points: int = 50,
) -> list[SelectivePoint]:
    """RC curve: risk over the top-k most confident items.

    Items are ranked by confidence (descending, stable); each point
    keeps the top-k items for evenly spaced k in ``[1, n]``.  The
    point's ``threshold`` is the marginal (k-th) confidence.  This
    rank-based construction is exact under ties — a confidence value
    shared by every item still yields the honest horizontal curve
    instead of a collapsed two-point artifact.
    """
    y, p = _check_inputs(correct, confidences)
    if n_points < 2:
        raise EvalError(f"n_points must be >= 2, got {n_points}")
    n = len(p)
    order = sorted(range(n), key=lambda i: p[i], reverse=True)
    ranked_y = [y[i] for i in order]
    ranked_p = [p[i] for i in order]
    ks = _k_grid(n, n_points)

    points: list[SelectivePoint] = []
    cum_loss = 0
    cursor = 0
    for k in ks:
        while cursor < k:
            cum_loss += 1 - ranked_y[cursor]
            cursor += 1
        risk = cum_loss / k
        points.append(SelectivePoint(
            threshold=ranked_p[k - 1],
            coverage=k / n,
            risk=risk,
            accuracy=1.0 - risk,
            n=k,
        ))
    return points



def _area_trapz(points: Sequence[SelectivePoint]) -> float:
    ordered = sorted(points, key=lambda pt: pt.coverage)
    area = 0.0
    for a, b in itertools.pairwise(ordered):
        area += (b.coverage - a.coverage) * (a.risk + b.risk) / 2.0
    return area


def aurc(curve: Sequence[SelectivePoint]) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    if not curve:
        raise EvalError("cannot compute AURC of an empty curve")
    return _area_trapz(curve)


def _k_grid(n: int, n_points: int) -> list[int]:
    """Evenly spaced k values in [1, n]; the full-coverage point last."""
    if n_points >= n:
        return list(range(1, n + 1))
    ks = sorted({round(1 + i * (n - 1) / (n_points - 1))
                 for i in range(n_points)})
    ks[-1] = n
    return ks


def oracle_aurc(correct: Sequence[int],
                confidences: Sequence[float],
                n_points: int = 50) -> float:
    """Best achievable AURC: keep items in order of true loss.

    Built on the same k-grid as :func:`risk_coverage_curve`, so
    ``aurc - oracle_aurc`` is pure ranking signal, not quadrature
    residue.
    """
    y, _p = _check_inputs(correct, confidences)
    # Oracle ranking: all correct items first (loss 0), then wrong.
    n = len(y)
    n_correct = sum(y)
    points: list[SelectivePoint] = []
    for k in _k_grid(n, n_points):
        kept_wrong = max(0, k - n_correct)
        points.append(SelectivePoint(
            threshold=float("nan"), coverage=k / n,
            risk=kept_wrong / k, accuracy=1.0 - kept_wrong / k, n=k))
    return _area_trapz(points)


def coverage_at_risk(curve: Sequence[SelectivePoint],
                     target_risk: float) -> float:
    """Largest coverage whose risk stays <= ``target_risk``."""
    if not 0.0 <= target_risk <= 1.0:
        raise EvalError(f"target_risk must be in [0, 1], got {target_risk}")
    best = 0.0
    for pt in curve:
        if pt.risk <= target_risk and pt.coverage > best:
            best = pt.coverage
    return best


def risk_at_coverage(curve: Sequence[SelectivePoint],
                     target_coverage: float) -> float:
    """Risk at ``target_coverage`` (linear interpolation on the curve)."""
    if not 0.0 < target_coverage <= 1.0:
        raise EvalError(
            f"target_coverage must be in (0, 1], got {target_coverage}")
    ordered = sorted(curve, key=lambda pt: pt.coverage)
    if target_coverage <= ordered[0].coverage:
        return ordered[0].risk
    for a, b in itertools.pairwise(ordered):
        if a.coverage <= target_coverage <= b.coverage:
            if b.coverage == a.coverage:
                return a.risk
            frac = ((target_coverage - a.coverage)
                    / (b.coverage - a.coverage))
            return a.risk + frac * (b.risk - a.risk)
    return ordered[-1].risk


@dataclass
class SelectiveReport:
    """Per-backend selective-risk results (slice 362)."""

    backends: dict[str, dict[str, Any]]
    n_items: int
    policy_threshold: float | None = None

    def excess_aurc(self, backend: str) -> float:
        """AURC minus oracle AURC: ranking quality (lower is better)."""
        info = self._backend(backend)
        return info["aurc"] - info["oracle_aurc"]

    def best_ranking(self) -> str | None:
        """Backend with the smallest excess AURC."""
        if not self.backends:
            return None
        return min(self.backends, key=self.excess_aurc)

    def coverage_at_risk(self, backend: str, target_risk: float) -> float:
        info = self._backend(backend)
        curve = [SelectivePoint(**pt) for pt in info["curve"]]
        return coverage_at_risk(curve, target_risk)

    def _backend(self, backend: str) -> dict[str, Any]:
        try:
            return self.backends[backend]
        except KeyError:
            raise EvalError(f"unknown backend {backend!r}") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info) for b, info in self.backends.items()},
            "n_items": self.n_items,
            "policy_threshold": self.policy_threshold,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SelectiveReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            n_items=data["n_items"],
            policy_threshold=data.get("policy_threshold"),
        )


def selective_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    policy: DecisionPolicy | None = None,
    n_points: int = 50,
    max_items: int | None = None,
) -> SelectiveReport:
    """Evaluate backends and score their selective-prediction quality."""
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("selective evaluation needs at least one item")

    names = list(backends) if backends is not None \
        else [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise EvalError("no backends available for this dataset's spec")

    report_backends: dict[str, dict[str, Any]] = {}
    for backend in names:
        correct: list[int] = []
        confidences: list[float] = []
        abstained = 0
        for item in items:
            expected = item.get("expected")
            try:
                result = gate.decide(
                    dict(item["state"]), spec, policy,
                    backend_name=backend)
            except Abstention:
                abstained += 1
                continue
            if expected is None or result.value is None:
                continue
            if isinstance(expected, list):
                hit = set(result.value or []) == set(expected)
            else:
                hit = result.value == expected
            correct.append(1 if hit else 0)
            confidences.append(float(result.probability))
        if not correct:
            raise EvalError(
                f"backend {backend!r} produced no scored items "
                f"({abstained} abstentions)"
            )
        curve = risk_coverage_curve(correct, confidences, n_points)
        curve_aurc = aurc(curve)
        oracle = oracle_aurc(correct, confidences, n_points)
        # Where does the gate's own abstention threshold sit?  Kept =
        # confidence >= minimum_probability, computed exactly.
        own = policy.minimum_probability
        kept_n = sum(1 for c in confidences if c >= own)
        kept_risk = (
            sum(1 - y for y, c in zip(correct, confidences, strict=True)
                if c >= own) / kept_n if kept_n else 0.0
        )
        own_point = SelectivePoint(
            threshold=own,
            coverage=kept_n / len(confidences),
            risk=kept_risk,
            accuracy=1.0 - kept_risk,
            n=kept_n,
        )
        report_backends[backend] = {
            "curve": [pt.to_dict() for pt in curve],
            "aurc": curve_aurc,
            "oracle_aurc": oracle,
            "excess_aurc": curve_aurc - oracle,
            "n_decided": len(correct),
            "n_abstained": abstained,
            "policy_threshold_point": own_point.to_dict(),
        }
    return SelectiveReport(
        backends=report_backends,
        n_items=len(items),
        policy_threshold=policy.minimum_probability,
    )
