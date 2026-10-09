"""Performance regression gates — measure, compare, fail loudly.

Slice 298. A gate binds a named workload metric to a committed
baseline artifact::

    gate = PerfGate()
    gate.add_gate("cache.get_hit_us", measure_cache_get_hit,
                  direction="lower-better", max_regression_frac=0.15)
    gate.check()  # raises PerfGateError listing every breached gate

- Metrics run ``samples`` times; the median is compared (medians
  resist the VM noise that poisons means — see slice 292).
- ``direction`` is ``"lower-better"`` (latency) or
  ``"higher-better"`` (throughput).
- Baselines live in ``benchmarks/perf_baseline.json``
  (``record_baseline()`` writes it; the file is committed).
- A breach raises :class:`PerfGateError` — deliberately *not*
  recoverable. Fix the regression or consciously re-baseline; never
  catch-and-retry a gate.

The default gate set (:func:`default_gates`) covers the hot paths
hardened in slices 292-293: cache key computation and cache hits.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hugrgate.errors import PerfGateError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "GateDefinition",
    "GateResult",
    "PerfGate",
    "default_gates",
]

DEFAULT_BASELINE_PATH = Path("benchmarks/perf_baseline.json")


@dataclass
class GateDefinition:
    """One registered gate."""
    name: str
    metric_fn: Callable[[], float]
    direction: str  # "lower-better" | "higher-better"
    max_regression_frac: float
    samples: int = 7
    unit: str = ""


@dataclass
class GateResult:
    """Outcome of one gate evaluation."""
    name: str
    baseline: float
    measured: float
    direction: str
    max_regression_frac: float
    regression_frac: float  # > 0 means regressed
    passed: bool
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "baseline": self.baseline,
            "measured": self.measured,
            "direction": self.direction,
            "max_regression_frac": self.max_regression_frac,
            "regression_frac": self.regression_frac,
            "passed": self.passed,
            "unit": self.unit,
        }


def _regression_frac(direction: str, baseline: float,
                     measured: float) -> float:
    if baseline == 0:
        return 0.0 if measured == 0 else float("inf")
    if direction == "lower-better":
        return (measured - baseline) / abs(baseline)
    return (baseline - measured) / abs(baseline)


class PerfGate:
    """Named performance regression gates over a baseline artifact."""

    def __init__(self, baseline_path: str | Path = DEFAULT_BASELINE_PATH
                 ) -> None:
        self._baseline_path = Path(baseline_path)
        self._gates: dict[str, GateDefinition] = {}

    def add_gate(self, name: str, metric_fn: Callable[[], float], *,
                 direction: str = "lower-better",
                 max_regression_frac: float = 0.15,
                 samples: int = 7, unit: str = "") -> None:
        """Register a gate."""
        if not name:
            raise PerfGateError("gate name must be non-empty")
        if direction not in ("lower-better", "higher-better"):
            raise PerfGateError(
                f"direction must be 'lower-better' or 'higher-better', "
                f"got {direction!r}")
        if not 0 < max_regression_frac < 10:
            raise PerfGateError(
                f"max_regression_frac must be in (0, 10), got "
                f"{max_regression_frac!r}")
        if samples < 1:
            raise PerfGateError(f"samples must be >= 1, got {samples!r}")
        if not callable(metric_fn):
            raise PerfGateError("metric_fn must be callable")
        if name in self._gates:
            raise PerfGateError(f"gate {name!r} already registered")
        self._gates[name] = GateDefinition(
            name=name, metric_fn=metric_fn, direction=direction,
            max_regression_frac=max_regression_frac, samples=samples,
            unit=unit)

    # -- baselines -------------------------------------------------------------------

    def load_baseline(self) -> dict[str, dict[str, Any]]:
        if not self._baseline_path.exists():
            raise PerfGateError(
                f"baseline artifact missing: {self._baseline_path}; run "
                f"record_baseline() first")
        try:
            data = json.loads(self._baseline_path.read_text(
                encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PerfGateError(
                f"cannot read baseline {self._baseline_path}: {e}") from e
        if not isinstance(data, dict) or "gates" not in data:
            raise PerfGateError(
                f"baseline {self._baseline_path} has no 'gates' object")
        return data["gates"]

    def record_baseline(self) -> dict[str, float]:
        """Measure every gate and write the baseline artifact."""
        measured = {name: self._measure(g)
                    for name, g in self._gates.items()}
        artifact = {
            "slice": 298,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "gates": {
                name: {
                    "value": value,
                    "direction": self._gates[name].direction,
                    "samples": self._gates[name].samples,
                    "unit": self._gates[name].unit,
                }
                for name, value in measured.items()
            },
        }
        self._baseline_path.parent.mkdir(parents=True, exist_ok=True)
        self._baseline_path.write_text(
            json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        logger.info("perfgate: recorded %d baselines to %s", len(measured),
                    self._baseline_path)
        return measured

    # -- evaluation ----------------------------------------------------------------------

    def _measure(self, gate: GateDefinition) -> float:
        samples = []
        for _ in range(gate.samples):
            try:
                samples.append(float(gate.metric_fn()))
            except PerfGateError:
                raise
            except Exception as e:
                raise PerfGateError(
                    f"metric_fn for gate {gate.name!r} raised "
                    f"{type(e).__name__}: {e}") from e
        return statistics.median(samples)

    def evaluate(self) -> list[GateResult]:
        """Run every gate against the baseline; return per-gate results."""
        baseline = self.load_baseline()
        results = []
        for name, gate in self._gates.items():
            if name not in baseline:
                raise PerfGateError(
                    f"gate {name!r} has no baseline; re-run "
                    f"record_baseline()")
            base = baseline[name]
            if base["direction"] != gate.direction:
                raise PerfGateError(
                    f"gate {name!r}: direction changed since baseline "
                    f"({base['direction']} -> {gate.direction}); "
                    f"re-baseline consciously")
            measured = self._measure(gate)
            reg = _regression_frac(gate.direction, float(base["value"]),
                                   measured)
            passed = reg <= gate.max_regression_frac
            results.append(GateResult(
                name=name, baseline=float(base["value"]),
                measured=measured, direction=gate.direction,
                max_regression_frac=gate.max_regression_frac,
                regression_frac=reg, passed=passed, unit=gate.unit))
            logger.info("perfgate: %s baseline=%.4g measured=%.4g "
                        "regression=%+.1f%% %s", name, base["value"],
                        measured, reg * 100,
                        "PASS" if passed else "FAIL")
        return results

    def check(self) -> list[GateResult]:
        """Evaluate; raise PerfGateError listing every breached gate."""
        results = self.evaluate()
        failed = [r for r in results if not r.passed]
        if failed:
            detail = "; ".join(
                f"{r.name}: regression {r.regression_frac * 100:+.1f}% "
                f"(baseline {r.baseline:.4g}{r.unit}, measured "
                f"{r.measured:.4g}{r.unit}, allowed "
                f"+{r.max_regression_frac * 100:.0f}%)"
                for r in failed)
            raise PerfGateError(
                f"{len(failed)}/{len(results)} performance gates "
                f"breached: {detail}")
        return results


# --- default gate set ----------------------------------------------------------------------

def _median_us(fn: Callable[[], Any], iters: int = 2000) -> float:
    fn()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(samples)


def _cache_key_metric() -> float:
    from hugrgate import DecisionPolicy, DecisionSpec
    from hugrgate.cache import cache_key
    state = {f"k{i}": i for i in range(12)}
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.1)
    return _median_us(lambda: cache_key(state, spec, policy))


def _cache_hit_metric() -> float:
    from hugrgate import DecisionPolicy, DecisionSpec
    from hugrgate.cache import DecisionCache
    from hugrgate.result import DecisionResult
    state = {f"k{i}": i for i in range(12)}
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.1)
    result = DecisionResult(value="a", probability=0.9,
                            distribution={"a": 0.9, "b": 0.1},
                            backend="perfgate", latency_ms=1.0)
    cache = DecisionCache()
    cache.put(state, spec, policy, result)
    return _median_us(lambda: cache.get(state, spec, policy))


def default_gates() -> list[tuple]:
    """The committed default gate set (name, metric_fn, kwargs)."""
    return [
        ("cache.key_us", _cache_key_metric,
         {"direction": "lower-better", "max_regression_frac": 0.25,
          "unit": "us"}),
        ("cache.get_hit_us", _cache_hit_metric,
         {"direction": "lower-better", "max_regression_frac": 0.25,
          "unit": "us"}),
    ]
