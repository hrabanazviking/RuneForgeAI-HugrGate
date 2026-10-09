"""Million-decision benchmark — sustained decision throughput. Slice 299.

Runs ``n`` real :meth:`HugrGate.decide` calls end to end (spec
validation, backend routing, backend evaluation, result validation,
provenance) and reports throughput, latency percentiles, RSS delta,
and error count.

The benchmark backend is deliberately instant and deterministic: the
point is to measure the *gate pipeline*, not any particular model.
States come from a seeded pool (``state_pool_size`` distinct states,
cycled), so the workload is reproducible.  Whatever the pipeline
does per decision — including any caching the gate performs — is
part of the honest number; the artifact records the exact setup.

``benchmarks/million_decisions.py`` runs the full 1M once and writes
``benchmarks/million_decisions.json``.  Tests use small ``n``.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.log import get_logger
from hugrgate.result import DecisionResult

logger = get_logger(__name__)

__all__ = [
    "InstantBackend",
    "MillionResult",
    "run_million",
]


class InstantBackend(Backend):
    """Deterministic instant backend: measures the pipeline, not a model."""

    name = "instant"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state: Any, spec: DecisionSpec,
                 context: Any = None) -> DecisionResult:
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.1},
                              backend=self.name, latency_ms=0.0)


@dataclass
class MillionResult:
    """Outcome of one benchmark run."""
    n: int
    seed: int
    state_pool_size: int
    elapsed_s: float
    decisions_per_s: float
    latency_p50_us: float
    latency_p95_us: float
    latency_p99_us: float
    latency_max_us: float
    errors: int
    rss_before_mb: float | None
    rss_after_mb: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "seed": self.seed,
            "state_pool_size": self.state_pool_size,
            "elapsed_s": self.elapsed_s,
            "decisions_per_s": self.decisions_per_s,
            "latency_us": {
                "p50": self.latency_p50_us,
                "p95": self.latency_p95_us,
                "p99": self.latency_p99_us,
                "max": self.latency_max_us,
            },
            "errors": self.errors,
            "rss_mb": {"before": self.rss_before_mb,
                       "after": self.rss_after_mb},
        }


def _rss_mb() -> float | None:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except (ImportError, OSError):
        return None


def run_million(n: int = 1_000_000, *, seed: int = 299,
                state_pool_size: int = 1000,
                progress_every: int = 100_000,
                sample_every: int = 100) -> MillionResult:
    """Run ``n`` decisions through a real gate; return measurements.

    Latency is sampled every ``sample_every``-th decision (systematic
    sampling keeps the overhead negligible at 1M).
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if sample_every < 1:
        raise ValueError(f"sample_every must be >= 1, got {sample_every}")
    rng = random.Random(seed)
    gate = HugrGate()
    gate.register(InstantBackend())
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.1)
    pool = [{f"f{i}": rng.random()} for _ in range(state_pool_size)
            for i in range(4)][:state_pool_size]

    # Warmup: stabilize caches, allocator, and branch prediction.
    for i in range(min(2000, n)):
        gate.decide(pool[i % state_pool_size], spec, policy)

    latencies: list[float] = []
    errors = 0
    rss_before = _rss_mb()
    t0 = time.perf_counter()
    for i in range(n):
        state = pool[i % state_pool_size]
        if i % sample_every == 0:
            t1 = time.perf_counter()
            try:
                gate.decide(state, spec, policy)
            except Exception:  # noqa: BLE001 - counting errors is the job
                errors += 1
            latencies.append((time.perf_counter() - t1) * 1e6)
        else:
            try:
                gate.decide(state, spec, policy)
            except Exception:  # noqa: BLE001 - counting errors is the job
                errors += 1
        if progress_every and (i + 1) % progress_every == 0:
            done = i + 1
            rate = done / (time.perf_counter() - t0)
            logger.info("millionbench: %d/%d (%.0f decisions/s)",
                        done, n, rate)
    elapsed = time.perf_counter() - t0
    rss_after = _rss_mb()

    ordered = sorted(latencies)
    def pct(p: float) -> float:
        return ordered[min(int(len(ordered) * p), len(ordered) - 1)]
    return MillionResult(
        n=n, seed=seed, state_pool_size=state_pool_size,
        elapsed_s=elapsed, decisions_per_s=n / elapsed,
        latency_p50_us=pct(0.50), latency_p95_us=pct(0.95),
        latency_p99_us=pct(0.99), latency_max_us=ordered[-1],
        errors=errors, rss_before_mb=rss_before, rss_after_mb=rss_after)
