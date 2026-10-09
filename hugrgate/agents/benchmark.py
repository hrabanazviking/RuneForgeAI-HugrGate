"""Agent Nervous System (Campaign XVI) — agent-system benchmark.

Slice 399.  The simulator (398) rehearses failure; the benchmark
*measures* it.  :class:`AgentBenchmark` runs named scenarios
through fresh simulators, repetitions each, and aggregates:

- success rate (mean ± min/max across repetitions);
- loops detected, runaways, escalations, failures (totals);
- wall-clock latency p50/p95 per scenario run (honest numbers
  from :func:`time.perf_counter`, not simulated time).

``sim_factory`` builds a new :class:`AgentSimulator` per run so
repetitions are isolated — no shared bus, breaker, or guard
state leaks between runs.  Seeds derive deterministically from
the base seed (``seed + rep``), so the whole benchmark replays.
:class:`BenchmarkReport` is wire-safe (:meth:`to_dict`) for CI
gates and the release gate (400).
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.simulator import AgentSimulator, SimulationReport

__all__ = [
    "AgentBenchmark",
    "AgentBenchmarkConfig",
    "BenchmarkReport",
    "ScenarioResult",
]


@dataclass(frozen=True)
class AgentBenchmarkConfig:
    """What to measure."""

    scenarios: Mapping[str, list[dict[str, Any]]]
    repetitions: int = 5
    seed: int = 0

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ValueError("scenarios must not be empty")
        if self.repetitions < 1:
            raise ValueError("repetitions must be >= 1")


@dataclass(frozen=True)
class ScenarioResult:
    """Aggregated measurements for one scenario."""

    name: str
    runs: int
    success_rate_mean: float
    success_rate_min: float
    success_rate_max: float
    total_failures: int
    total_loops: int
    total_runaways: int
    total_escalations: int
    latency_p50_ms: float
    latency_p95_ms: float


@dataclass(frozen=True)
class BenchmarkReport:
    """The full benchmark outcome."""

    scenarios: tuple[ScenarioResult, ...]
    repetitions: int
    seed: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Wire-safe representation."""
        return {
            "repetitions": self.repetitions,
            "seed": self.seed,
            "notes": list(self.notes),
            "scenarios": [
                {
                    "name": s.name,
                    "runs": s.runs,
                    "success_rate_mean": s.success_rate_mean,
                    "success_rate_min": s.success_rate_min,
                    "success_rate_max": s.success_rate_max,
                    "total_failures": s.total_failures,
                    "total_loops": s.total_loops,
                    "total_runaways": s.total_runaways,
                    "total_escalations": s.total_escalations,
                    "latency_p50_ms": s.latency_p50_ms,
                    "latency_p95_ms": s.latency_p95_ms,
                }
                for s in self.scenarios
            ],
        }


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


class AgentBenchmark:
    """Benchmarks agent systems across scenarios and repetitions."""

    def run(
        self,
        sim_factory: Callable[[], AgentSimulator],
        config: AgentBenchmarkConfig,
    ) -> BenchmarkReport:
        """Run every scenario ``repetitions`` times; aggregate."""
        results: list[ScenarioResult] = []
        notes: list[str] = []
        for name, script in config.scenarios.items():
            rates: list[float] = []
            latencies: list[float] = []
            totals = {"failures": 0, "loops": 0, "runaways": 0,
                      "escalations": 0}
            for rep in range(config.repetitions):
                sim = sim_factory()
                start = time.perf_counter()
                report: SimulationReport = sim.run(
                    script, seed=config.seed + rep)
                latencies.append((time.perf_counter() - start) * 1000.0)
                rates.append(report.success_rate)
                totals["failures"] += report.failures
                totals["loops"] += report.loops_detected
                totals["runaways"] += report.runaways
                totals["escalations"] += report.escalations
            lat_sorted = sorted(latencies)
            results.append(ScenarioResult(
                name=name,
                runs=config.repetitions,
                success_rate_mean=round(statistics.fmean(rates), 4),
                success_rate_min=round(min(rates), 4),
                success_rate_max=round(max(rates), 4),
                total_failures=totals["failures"],
                total_loops=totals["loops"],
                total_runaways=totals["runaways"],
                total_escalations=totals["escalations"],
                latency_p50_ms=round(_percentile(lat_sorted, 50), 3),
                latency_p95_ms=round(_percentile(lat_sorted, 95), 3),
            ))
            if min(rates) < max(rates):
                notes.append(
                    f"scenario {name!r}: nondeterministic across "
                    f"repetitions ({min(rates):.2f}..{max(rates):.2f})")
        return BenchmarkReport(
            scenarios=tuple(results),
            repetitions=config.repetitions,
            seed=config.seed,
            notes=tuple(notes),
        )
