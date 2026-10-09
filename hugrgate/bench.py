"""Benchmark harness — datasets → backends → metrics. Slice 45.

Runs a labeled (or unlabeled) dataset through one or more backends and
reports:

- ``accuracy`` — exact-match rate (categorical / ordinal / binary;
  set-equality for multilabel; skipped for numeric)
- ``brier_score`` — mean squared error of the full distribution
  against the one-hot truth
- ``ece`` — expected calibration error over 10 confidence bins
- ``latency_p50_ms`` / ``latency_p99_ms`` — from ``result.latency_ms``
- ``throughput_per_s`` — decisions per wall-clock second
- ``abstention_rate`` — fraction of items the gate abstained on

The report is a plain JSON-serializable dict (see :func:`run_benchmark`),
renderable to markdown by :mod:`hugrgate.bench_report`.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from hugrgate import (
    Abstention,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    HugrGate,
)
from hugrgate import __version__ as HUGRGATE_VERSION

__all__ = [
    "accuracy",
    "brier_score",
    "reliability_bins",
    "expected_calibration_error",
    "dataset_fingerprint",
    "BenchmarkConfig",
    "run_benchmark",
    "Benchmark",
]


# ---------------------------------------------------------------------------
# Metric primitives
# ---------------------------------------------------------------------------

def accuracy(results: List[Tuple[Any, DecisionResult]]) -> Optional[float]:
    """Exact-match rate. ``None`` when no item has a usable expected value."""
    scored = [(exp, res) for exp, res in results
              if exp is not None and res.value is not None]
    if not scored:
        return None
    hits = 0
    for expected, result in scored:
        if isinstance(expected, list):  # multilabel: set equality
            if set(result.value) == set(expected):
                hits += 1
        elif result.value == expected:
            hits += 1
    return hits / len(scored)


def brier_score(results: List[Tuple[Any, DecisionResult]],
                spec: DecisionSpec) -> Optional[float]:
    """Mean squared error between predicted distribution and one-hot truth."""
    if spec.type in ("numeric", "multilabel"):
        return None
    space = spec.value_space()
    scored = [(exp, res) for exp, res in results
              if exp is not None and res.distribution]
    if not scored:
        return None
    total = 0.0
    for expected, result in scored:
        for outcome in space:
            truth = 1.0 if outcome == expected else 0.0
            total += (result.distribution.get(outcome, 0.0) - truth) ** 2
    return total / len(scored)


def reliability_bins(results: List[Tuple[Any, DecisionResult]],
                     n_bins: int = 10) -> List[Dict[str, Any]]:
    """Bin items by predicted-class confidence; report acc vs confidence."""
    scored = [(exp, res) for exp, res in results
              if exp is not None and res.value is not None]
    bins: List[Dict[str, Any]] = [
        {"bin_low": i / n_bins, "bin_high": (i + 1) / n_bins,
         "count": 0, "accuracy": 0.0, "avg_confidence": 0.0}
        for i in range(n_bins)
    ]
    for expected, result in scored:
        idx = min(int(result.probability * n_bins), n_bins - 1)
        b = bins[idx]
        b["count"] += 1
        hit = 1.0
        if isinstance(expected, list):
            hit = 1.0 if set(result.value) == set(expected) else 0.0
        elif result.value != expected:
            hit = 0.0
        b["accuracy"] += hit
        b["avg_confidence"] += result.probability
    for b in bins:
        if b["count"]:
            b["accuracy"] /= b["count"]
            b["avg_confidence"] /= b["count"]
    return bins


def expected_calibration_error(results: List[Tuple[Any, DecisionResult]],
                               n_bins: int = 10) -> Optional[float]:
    """ECE = sum_b |acc_b - conf_b| * (n_b / n)."""
    scored = [(exp, res) for exp, res in results
              if exp is not None and res.value is not None]
    if not scored:
        return None
    ece = 0.0
    for b in reliability_bins(results, n_bins):
        if b["count"]:
            ece += abs(b["accuracy"] - b["avg_confidence"]) * b["count"]
    return ece / len(scored)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


# ---------------------------------------------------------------------------
# Dataset handling
# ---------------------------------------------------------------------------

def dataset_fingerprint(dataset: Mapping[str, Any]) -> str:
    """Stable sha256 over the dataset's items (reproducibility anchor)."""
    payload = json.dumps(dataset.get("items", []), sort_keys=True,
                         default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class BenchmarkConfig:
    backends: Optional[List[str]] = None  # None → all supporting
    policy: Optional[DecisionPolicy] = None
    max_items: Optional[int] = None


def _evaluate_one(gate: HugrGate, item: Mapping[str, Any],
                  spec: DecisionSpec, policy: DecisionPolicy,
                  backend_name: str) -> Tuple[Any, Optional[DecisionResult],
                                             bool]:
    """Returns (expected, result|None, abstained)."""
    expected = item.get("expected")
    try:
        result = gate.decide(dict(item["state"]), spec, policy,
                             backend_name=backend_name)
    except Abstention:
        return expected, None, True
    return expected, result, False


def run_benchmark(dataset: Mapping[str, Any], gate: HugrGate,
                  backends: Optional[List[str]] = None,
                  policy: Optional[DecisionPolicy] = None,
                  max_items: Optional[int] = None) -> Dict[str, Any]:
    """Run ``dataset`` through each backend; return the JSON report dict."""
    spec = DecisionSpec.from_dict(dataset["spec"])
    policy = policy or DecisionPolicy()
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]

    names = backends or [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise ValueError("no backends available for this dataset's spec")

    report: Dict[str, Any] = {
        "hugrgate_version": HUGRGATE_VERSION,
        "dataset": dataset.get("name", "unnamed"),
        "dataset_version": dataset.get("version", "unknown"),
        "dataset_fingerprint": dataset_fingerprint(dataset),
        "n_items": len(items),
        "spec": spec.to_dict(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "platform": {"system": platform.system(),
                     "release": platform.release(),
                     "machine": platform.machine(),
                     "python": platform.python_version(),
                     "processor": platform.processor() or "unknown"},
        "backends": {},
    }

    for name in names:
        pairs: List[Tuple[Any, DecisionResult]] = []
        latencies: List[float] = []
        abstentions = 0
        errors = 0
        wall_start = time.perf_counter()
        for item in items:
            expected, result, abstained = _evaluate_one(
                gate, item, spec, policy, name)
            if abstained:
                abstentions += 1
                continue
            if result is None:
                errors += 1
                continue
            pairs.append((expected, result))
            latencies.append(result.latency_ms)
        wall_s = time.perf_counter() - wall_start

        bins = reliability_bins(pairs)
        metrics: Dict[str, Any] = {
            "n_decided": len(pairs),
            "n_abstained": abstentions,
            "n_errors": errors,
            "abstention_rate": abstentions / len(items) if items else 0.0,
            "accuracy": accuracy(pairs),
            "brier_score": brier_score(pairs, spec),
            "ece": expected_calibration_error(pairs),
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p99_ms": _percentile(latencies, 99),
            "latency_mean_ms": (sum(latencies) / len(latencies)
                                if latencies else 0.0),
            "throughput_per_s": (len(pairs) / wall_s) if wall_s > 0 else 0.0,
            "reliability_bins": bins,
            "backend": name,
            "model": "unknown",
            "calibration": (gate.registry.get(name).calibration_info()
                            if gate.registry.get(name) else {}),
        }
        report["backends"][name] = metrics

    return report


def _weighted_mean(values: List[Tuple[float, float]]) -> Optional[float]:
    """Mean of values weighted by weights; None if all values are None."""
    total_w = sum(w for v, w in values if v is not None)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in values if v is not None) / total_w


class Benchmark:
    """Convenience runner: ``Benchmark(gate, dataset).run(backends)``.

    Accepts two dataset shapes:

    - a list of ``{"state", "expected", "spec"}`` items (per-item specs),
    - a dict ``{"spec", "items": [{"state", "expected", ...}]}``
      (shared spec, as produced by ``benchmarks/build.py``).

    Items are grouped by spec; each group runs through
    :func:`run_benchmark` and the metrics are merged (accuracy/Brier/ECE
    as decided-count-weighted means; latency percentiles as weighted
    means of the per-group percentiles — an approximation documented
    here rather than hidden).
    """

    def __init__(self, gate: HugrGate, dataset: Any) -> None:
        self.gate = gate
        self.dataset = dataset

    def _groups(self) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        if isinstance(self.dataset, dict):
            spec = self.dataset["spec"]
            items = [{"state": i["state"], "expected": i.get("expected")}
                     for i in self.dataset.get("items", [])]
            return [(spec, items)]
        groups: Dict[str, Tuple[Dict[str, Any], List[Dict[str, Any]]]] = {}
        for item in self.dataset:
            key = json.dumps(item["spec"], sort_keys=True, default=str)
            if key not in groups:
                groups[key] = (item["spec"], [])
            groups[key][1].append({"state": item["state"],
                                   "expected": item.get("expected")})
        return list(groups.values())

    def run(self, backends: Optional[List[str]] = None,
            policy: Optional[DecisionPolicy] = None) -> Dict[str, Any]:
        merged: Dict[str, Dict[str, Any]] = {}
        n_groups = 0
        total_items = 0
        for spec_dict, items in self._groups():
            n_groups += 1
            total_items += len(items)
            dataset = {"name": "benchmark", "version": "adhoc",
                       "spec": spec_dict, "items": items}
            report = run_benchmark(dataset, self.gate, backends=backends,
                                   policy=policy)
            for name, m in report["backends"].items():
                slot = merged.setdefault(name, {"_w": []})
                slot["_w"].append(m)
        backends_out: Dict[str, Any] = {}
        for name, slot in merged.items():
            parts = slot["_w"]
            weights = [p["n_decided"] for p in parts]
            backends_out[name] = {
                "n_decided": sum(p["n_decided"] for p in parts),
                "n_abstained": sum(p["n_abstained"] for p in parts),
                "n_errors": sum(p["n_errors"] for p in parts),
                "abstention_rate": (
                    sum(p["n_abstained"] for p in parts) / total_items
                    if total_items else 0.0),
                "accuracy": _weighted_mean(
                    [(p["accuracy"], w) for p, w in zip(parts, weights)]),
                "brier_score": _weighted_mean(
                    [(p["brier_score"], w) for p, w in zip(parts, weights)]),
                "ece": _weighted_mean(
                    [(p["ece"], w) for p, w in zip(parts, weights)]),
                "latency_p50_ms": _weighted_mean(
                    [(p["latency_p50_ms"], w) for p, w in zip(parts, weights)]),
                "latency_p99_ms": _weighted_mean(
                    [(p["latency_p99_ms"], w) for p, w in zip(parts, weights)]),
                "throughput_per_s": sum(p["throughput_per_s"]
                                        for p in parts),
                "groups": n_groups,
            }
        return {"hugrgate_version": HUGRGATE_VERSION,
                "n_items": total_items,
                "groups": n_groups,
                "backends": backends_out}
