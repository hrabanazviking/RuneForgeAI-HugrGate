"""Ensemble benchmarks — measured, not promised. Slice 125 needs these
numbers; this slice produces them. Slice 124.

Reuses :mod:`hugrgate.bench` metrics (accuracy, Brier score, ECE) so
ensemble numbers are comparable with single-backend numbers:

- :func:`benchmark_strategies` — one fresh council per strategy over
  the same labeled states; per strategy: accuracy, Brier, ECE,
  wall-clock time;
- :func:`benchmark_scaling` — wall time vs council size;
- :func:`write_benchmark_report` — the JSON artifact.

Tests exercise the harness against ``tmp_path`` only and never touch
the committed artifact (Campaign III lesson); the real
``benchmarks/ensemble.json`` is regenerated via ``regenerate_ensemble_benchmarks()`` after
the final test run, before committing.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from hugrgate.backend import Backend
from hugrgate.bench import (
    accuracy,
    brier_score,
    dataset_fingerprint,
    expected_calibration_error,
)
from hugrgate.ensemble.api import Ensemble
from hugrgate.errors import PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "STRATEGIES_BENCHMARKED",
    "benchmark_scaling",
    "benchmark_strategies",
    "demo_council",
    "regenerate_ensemble_benchmarks",
    "write_benchmark_report",
]

STRATEGIES_BENCHMARKED = ("hard", "soft", "weighted", "confidence")

ARTIFACT = Path("benchmarks/ensemble.json")


def _metrics(pairs: list[tuple], spec: DecisionSpec,
             wall_ms: float) -> dict[str, Any]:
    latencies = [r.latency_ms for _, r in pairs]
    return {
        "n": len(pairs),
        "accuracy": accuracy(pairs),
        "brier_score": brier_score(pairs, spec),
        "ece": expected_calibration_error(pairs),
        "wall_ms": round(wall_ms, 3),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 3)
        if latencies else 0.0,
    }


def benchmark_strategies(
        member_factory: Callable[[], list[Backend]],
        states: list[Mapping[str, Any]],
        spec: DecisionSpec,
        labels: list[Any],
        strategies: list[str] | None = None,
        ensemble_kwargs: dict[str, Any] | None = None
        ) -> dict[str, dict[str, Any]]:
    """One fresh council per strategy; same states, same labels."""
    if strategies is None:
        strategies = list(STRATEGIES_BENCHMARKED)
    if len(states) != len(labels):
        raise PolicyError(
            f"{len(states)} states but {len(labels)} labels")
    if not states:
        raise PolicyError("benchmark_strategies needs states")
    if not strategies:
        raise PolicyError("benchmark_strategies needs strategies")
    ensemble_kwargs = ensemble_kwargs or {}
    report: dict[str, dict[str, Any]] = {}
    for strategy in strategies:
        members = member_factory()
        if not members:
            raise PolicyError("member_factory produced no members")
        ens = Ensemble(members, strategy=strategy, **ensemble_kwargs)
        start = time.perf_counter()
        results = ens.decide_batch(states, spec)
        wall_ms = (time.perf_counter() - start) * 1000.0
        pairs = list(zip(labels, results, strict=True))
        report[strategy] = _metrics(pairs, spec, wall_ms)
    return report


def benchmark_scaling(
        member_factory: Callable[[int], list[Backend]],
        states: list[Mapping[str, Any]],
        spec: DecisionSpec,
        sizes: list[int] | None = None,
        strategy: str = "soft") -> dict[str, dict[str, Any]]:
    """Wall time vs council size (same strategy throughout)."""
    if sizes is None:
        sizes = [1, 2, 3, 5]
    if not sizes:
        raise PolicyError("benchmark_scaling needs sizes")
    table: dict[str, dict[str, Any]] = {}
    for n in sizes:
        members = member_factory(n)
        if len(members) != n:
            raise PolicyError(
                f"member_factory({n}) produced {len(members)} members")
        ens = Ensemble(members, strategy=strategy)
        start = time.perf_counter()
        ens.decide_batch(states, spec)
        wall_ms = (time.perf_counter() - start) * 1000.0
        table[str(n)] = {
            "members": n,
            "states": len(states),
            "wall_ms": round(wall_ms, 3),
            "ms_per_state": round(wall_ms / len(states), 3)
            if states else 0.0,
        }
    return table


def write_benchmark_report(report: dict[str, Any],
                           path: Path | str) -> Path:
    """Write the JSON artifact (pretty, sorted keys)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True)
                   + "\n")
    return out


# --- demo council (artifact generation only) -------------------------------


class _DemoBackend(Backend):
    """Deterministic demo voter: right with probability ``skill``.

    Cycles a fixed correct/incorrect pattern — no RNG, so the
    committed artifact regenerates byte-identically.
    """

    def __init__(self, name: str, skill_num: int, skill_den: int,
                 classes: list[str]):
        self.name = name
        self._num = skill_num
        self._den = skill_den
        self._classes = classes
        self._calls = 0

    def capabilities(self) -> dict[str, Any]:
        return {"demo": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal")

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        label = state["label"]
        self._calls += 1
        # correct on the first _num of every _den calls
        correct = (self._calls - 1) % self._den < self._num
        value = label if correct else next(
            c for c in self._classes if c != label)
        rest = (0.2 / (len(self._classes) - 1)
                if len(self._classes) > 1 else 0.0)
        dist = {c: (0.8 if c == value else rest)
                for c in self._classes}
        return DecisionResult(value=value,
                              probability=dist[value],
                              distribution=dist,
                              backend=self.name)


def demo_council(n: int = 3) -> list[Backend]:
    """Three demo voters of descending skill (artifact use only)."""
    skills = [(4, 5), (3, 5), (3, 5), (2, 5), (2, 5)]
    classes = ["alpha", "beta", "gamma"]
    return [_DemoBackend(f"demo{i}", *skills[i % len(skills)],
                         classes)
            for i in range(n)]


def regenerate_ensemble_benchmarks() -> Path:
    """Regenerate the committed artifact. Run from the repo root."""
    classes = ["alpha", "beta", "gamma"]
    spec = DecisionSpec(type="categorical", options=classes)
    states: list[Mapping[str, Any]] = [
        {"x": i, "label": classes[i % 3]} for i in range(60)]
    labels = [s["label"] for s in states]
    dataset = {"items": [{"x": s["x"], "label": s["label"]}
                         for s in states]}
    report = {
        "dataset_fingerprint": dataset_fingerprint(dataset),
        "states": len(states),
        "strategies": benchmark_strategies(
            lambda: demo_council(3), states, spec, labels),
        "scaling": benchmark_scaling(demo_council, states, spec),
    }
    return write_benchmark_report(report, ARTIFACT)
