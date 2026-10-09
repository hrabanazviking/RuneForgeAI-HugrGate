"""Autotuning benchmark. Slice 474.

Claims about tuners need numbers. This module is the harness that
produces them: each :class:`BenchmarkScenario` runs one tuner
end-to-end through a real controller (offline mode, journaling
driver), then scores the *baseline config* and the *tuned config*
with the same replay evaluator on the same recorded data. The
reported improvement is therefore measured, never asserted.

A scenario needs:

- ``params``: the tunable parameters to register;
- ``tuner``: the tuner under test (seeded, deterministic);
- ``replay``: ``config -> float`` scoring a full config on recorded
  data (higher is better);
- ``data_fingerprint``: what the numbers were measured on.

:class:`AutotuneBenchmark.run` executes every scenario and returns
a :class:`BenchmarkReport` with per-scenario baseline/tuned scores,
improvement, wall time, and the proposal id behind the tuned
score. ``summary()`` renders a human-readable table. Reports are
plain data (``to_dict``); persisting them is the caller's job —
measurement artifacts (``benchmarks/*.json``) are never committed.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
)
from hugrgate.autotune.modes import OfflineDriver
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import AutotuneError

__all__ = [
    "AutotuneBenchmark",
    "BenchmarkReport",
    "BenchmarkResult",
    "BenchmarkScenario",
]


@dataclass
class BenchmarkScenario:
    """One tuner measured end-to-end."""

    name: str
    tuner: BaseTuner
    params: Sequence[TunableParameter]
    replay: Callable[[Mapping[str, Any]], float]
    data_fingerprint: str = ""
    baseline_note: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise AutotuneError("scenario needs a name")
        if not self.params:
            raise AutotuneError("scenario needs params", scenario=self.name)


@dataclass
class BenchmarkResult:
    """Measured outcome of one scenario."""

    scenario: str
    baseline_score: float
    tuned_score: float
    improvement: float
    seconds: float
    proposal_id: str
    data_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "baseline_score": self.baseline_score,
            "tuned_score": self.tuned_score,
            "improvement": self.improvement,
            "seconds": self.seconds,
            "proposal_id": self.proposal_id,
            "data_fingerprint": self.data_fingerprint,
        }


@dataclass
class BenchmarkReport:
    """The full measured report."""

    seed: int
    results: list[BenchmarkResult] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"seed": self.seed,
                "generated_at": self.generated_at,
                "results": [r.to_dict() for r in self.results]}

    def summary(self) -> str:
        lines = [f"autotune benchmark (seed={self.seed}):",
                 f"{'scenario':32} {'baseline':>10} {'tuned':>10} "
                 f"{'improv':>10} {'secs':>8}"]
        for r in self.results:
            lines.append(f"{r.scenario:32} {r.baseline_score:10.4f} "
                         f"{r.tuned_score:10.4f} {r.improvement:10.4f} "
                         f"{r.seconds:8.3f}")
        return "\n".join(lines)


class AutotuneBenchmark:
    """Run scenarios and measure tuner improvement over baseline."""

    def __init__(self, scenarios: Sequence[BenchmarkScenario]) -> None:
        if not scenarios:
            raise AutotuneError("benchmark needs at least one scenario")
        names = [s.name for s in scenarios]
        if len(set(names)) != len(names):
            raise AutotuneError("duplicate scenario names")
        self._scenarios = list(scenarios)

    def run(self, seed: int = 0) -> BenchmarkReport:
        report = BenchmarkReport(seed=seed)
        for scenario in self._scenarios:
            report.results.append(self._run_one(scenario, seed))
        return report

    def _run_one(self, scenario: BenchmarkScenario,
                 seed: int) -> BenchmarkResult:
        store = ConfigStore()
        for param in scenario.params:
            store.register(param)
        controller = OptimizationController(store=store)
        controller.register_objective(scenario.tuner.objective_id,
                                      lambda values: 0.0)
        controller.register_tuner(scenario.tuner)
        driver = OfflineDriver()
        controller.register_driver(driver)

        baseline_config = store.snapshot()
        try:
            baseline_score = float(scenario.replay(baseline_config))
        except Exception as exc:
            raise AutotuneError("benchmark replay evaluator raised "
                                "on baseline",
                                scenario=scenario.name,
                                error=repr(exc)) from exc

        started = time.time()
        controller.run_cycle(mode=Mode.OFFLINE, seed=seed)
        seconds = time.time() - started

        tuned_score = baseline_score
        proposal_id = ""
        for entry in driver.journal:
            pid = entry["proposal"]["proposal_id"]
            candidate = dict(baseline_config)
            candidate.update(entry["proposal"]["changes"])
            try:
                score = float(scenario.replay(candidate))
            except Exception as exc:
                raise AutotuneError("benchmark replay evaluator raised",
                                    scenario=scenario.name,
                                    error=repr(exc)) from exc
            if score > tuned_score:
                tuned_score = score
                proposal_id = pid
        return BenchmarkResult(
            scenario=scenario.name,
            baseline_score=baseline_score,
            tuned_score=tuned_score,
            improvement=tuned_score - baseline_score,
            seconds=seconds,
            proposal_id=proposal_id,
            data_fingerprint=scenario.data_fingerprint)
