"""Latency-aware evaluation — quality under time pressure. Slice 364.

:mod:`hugrgate.perfgate` gates latency *regressions* against committed
baselines; this module evaluates latency *quality tradeoffs*: which
backend stays useful when the clock is the constraint?

- :func:`latency_aware_evaluate` — evaluates backends once, collecting
  per-item ``(latency_ms, correct)`` pairs, and reports per backend:
  p50/p99/mean latency, SLO compliance (fraction of decisions within
  ``slo_ms``), budgeted accuracy (accuracy over in-SLO decisions
  only), and tail heaviness (p99/p50).
- :class:`LatencyReport` — per-backend results plus queries:
  :meth:`LatencyReport.meets_slo`, :meth:`LatencyReport.fastest`,
  :meth:`LatencyReport.best_budgeted_accuracy`.

A backend that is accurate but always late scores badly here *by
design*: budgeted accuracy is the honest number for SLO-bound
deployments.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "LatencyReport",
    "latency_aware_evaluate",
]


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    ordered = sorted(sorted_values)
    k = (len(ordered) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


@dataclass
class LatencyReport:
    """Per-backend latency/quality results + SLO queries (slice 364)."""

    backends: dict[str, dict[str, Any]]
    slo_ms: float
    n_items: int

    def meets_slo(self, backend: str, min_compliance: float = 1.0) -> bool:
        """True when ``backend``'s SLO compliance reaches the bar."""
        info = self._backend(backend)
        if not 0.0 <= min_compliance <= 1.0:
            raise EvalError(
                f"min_compliance must be in [0, 1], got {min_compliance}"
            )
        compliance = info["slo_compliance"]
        return (compliance is not None
                and compliance >= min_compliance)

    def fastest(self) -> str | None:
        """Backend with the lowest p50 latency."""
        scored = [(b, info["latency_p50_ms"])
                  for b, info in self.backends.items()
                  if info["latency_p50_ms"] is not None]
        if not scored:
            return None
        return min(scored, key=lambda kv: kv[1])[0]

    def best_budgeted_accuracy(self) -> tuple[str | None, float | None]:
        """(backend, budgeted_accuracy) maximizing in-SLO accuracy."""
        scored = [(b, info["budgeted_accuracy"])
                  for b, info in self.backends.items()
                  if isinstance(info["budgeted_accuracy"], (int, float))]
        if not scored:
            return None, None
        return max(scored, key=lambda kv: kv[1])

    def _backend(self, backend: str) -> dict[str, Any]:
        try:
            return self.backends[backend]
        except KeyError:
            raise EvalError(f"unknown backend {backend!r}") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info)
                         for b, info in self.backends.items()},
            "slo_ms": self.slo_ms,
            "n_items": self.n_items,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LatencyReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            slo_ms=data["slo_ms"],
            n_items=data["n_items"],
        )


def latency_aware_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    slo_ms: float = 100.0,
    policy: DecisionPolicy | None = None,
    max_items: int | None = None,
) -> LatencyReport:
    """Evaluate backends for latency behavior and in-SLO quality."""
    if not slo_ms > 0:
        raise EvalError(f"slo_ms must be positive, got {slo_ms}")
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("latency-aware evaluation needs at least one item")
    names = list(backends) if backends is not None \
        else [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise EvalError("no backends available for this dataset's spec")

    results: dict[str, dict[str, Any]] = {}
    for backend in names:
        latencies: list[float] = []
        in_slo_correct = 0
        in_slo_n = 0
        all_correct = 0
        n = 0
        abstained = 0
        for item in items:
            expected = item.get("expected")
            try:
                result: DecisionResult = gate.decide(
                    dict(item["state"]), spec, policy,
                    backend_name=backend)
            except Abstention:
                abstained += 1
                continue
            n += 1
            latencies.append(result.latency_ms)
            if expected is None or result.value is None:
                continue
            if isinstance(expected, list):
                hit = set(result.value or []) == set(expected)
            else:
                hit = result.value == expected
            if hit:
                all_correct += 1
            if result.latency_ms <= slo_ms:
                in_slo_n += 1
                if hit:
                    in_slo_correct += 1
        p50 = _percentile(latencies, 50)
        p99 = _percentile(latencies, 99)
        results[backend] = {
            "n_decided": n,
            "n_abstained": abstained,
            "accuracy": (all_correct / n) if n else None,
            "latency_p50_ms": p50 if n else None,
            "latency_p99_ms": p99 if n else None,
            "latency_mean_ms": (sum(latencies) / n) if n else None,
            "latency_max_ms": max(latencies) if latencies else None,
            "tail_heaviness": (p99 / p50) if p50 > 0 else None,
            "slo_compliance": (in_slo_n / n) if n else None,
            "budgeted_accuracy": (
                in_slo_correct / in_slo_n if in_slo_n else None
            ),
            "budgeted_n": in_slo_n,
        }
    return LatencyReport(backends=results, slo_ms=slo_ms,
                         n_items=len(items))
