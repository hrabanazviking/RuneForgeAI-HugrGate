"""Benchmark reproducibility audit (slice 495).

Benchmarks are only useful if they measure the code, not the
weather. This module provides:

- :func:`run_workload` — a deterministic decision workload
  (seeded states, fixed stub backend) returning a content digest
  plus timing;
- :func:`run_reproducibility_audit` — runs the workload ``runs``
  times and asserts (a) identical digests across runs
  (determinism) and (b) timing within a documented noise band;
- :func:`compare_with_baseline` — compares a fresh measurement
  against an explicit recorded baseline JSON (never invented).

Timing is inherently noisy; the audit is honest about that: the
digest assertion is exact, the timing assertion is a band.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "ReproReport",
    "compare_with_baseline",
    "run_reproducibility_audit",
    "run_workload",
]

#: Maximum acceptable coefficient of variation of ops/sec across
#: runs on one machine. Timing is noisy; beyond this the workload
#: itself is suspect (e.g. GC storms, thermal throttling).
MAX_TIMING_CV = 0.25

#: Maximum acceptable relative drift of ops/sec versus the recorded
#: baseline before the audit flags a regression-or-environment
#: change for human review.
MAX_BASELINE_DRIFT = 0.30


def run_workload(n: int = 2000, seed: int = 495) -> dict[str, Any]:
    """Run the deterministic workload; return digest + timing."""
    from hugrgate.backend import Backend
    from hugrgate.core import HugrGate
    from hugrgate.policy import DecisionPolicy
    from hugrgate.result import DecisionResult
    from hugrgate.security.input_limits import InputLimits
    from hugrgate.spec import DecisionSpec

    class _Stub(Backend):
        name = "repro-stub"

        def capabilities(self) -> dict[str, Any]:
            return {"spec_types": ["categorical"]}

        def supports(self, spec: DecisionSpec) -> bool:
            return True

        def evaluate(self, state, spec, context=None) -> DecisionResult:
            v = "a" if state["x"] >= 0.5 else "b"
            dist = {"a": 0.75, "b": 0.25} if v == "a" \
                else {"a": 0.25, "b": 0.75}
            return DecisionResult(value=v, probability=0.75,
                                  distribution=dist)

    rng = np.random.default_rng(seed)
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy()
    # Slice 492: batch limits are enforced; the benchmark opts in
    # explicitly rather than tripping the default ceiling.
    limits = InputLimits(max_batch_size=max(n, 1024))
    gate = HugrGate()
    gate.register(_Stub())
    try:
        states = [{"x": float(v)} for v in rng.uniform(0.0, 1.0, size=n)]
        # Warmup: fill caches, settle the allocator.
        gate.decide_batch(states[:64], spec, policy, limits=limits)
        start = time.perf_counter()
        results = gate.decide_batch(states, spec, policy, limits=limits)
        elapsed = time.perf_counter() - start
    finally:
        gate.close()
    digest_src = json.dumps(
        [(r.value, r.probability) for r in results], sort_keys=True)
    digest = hashlib.sha256(digest_src.encode()).hexdigest()
    return {
        "n": n,
        "seed": seed,
        "digest": digest,
        "elapsed_s": elapsed,
        "ops_per_sec": n / elapsed if elapsed > 0 else 0.0,
        "python": platform.python_version(),
        "machine": platform.machine(),
    }


@dataclass
class ReproReport:
    """Outcome of :func:`run_reproducibility_audit`."""

    runs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def digests(self) -> list[str]:
        return [r["digest"] for r in self.runs]

    @property
    def deterministic(self) -> bool:
        return len(set(self.digests)) == 1

    @property
    def timing_cv(self) -> float:
        rates = np.array([r["ops_per_sec"] for r in self.runs])
        mean = rates.mean()
        return float(rates.std() / mean) if mean > 0 else float("inf")

    @property
    def timing_stable(self) -> bool:
        return self.timing_cv <= MAX_TIMING_CV

    @property
    def passed(self) -> bool:
        return bool(self.runs) and self.deterministic and self.timing_stable


def run_reproducibility_audit(runs: int = 3, n: int = 2000,
                              seed: int = 495) -> ReproReport:
    """Run the workload ``runs`` times and audit reproducibility."""
    return ReproReport(
        runs=[run_workload(n=n, seed=seed) for _ in range(runs)])


def compare_with_baseline(measurement: dict[str, Any],
                          baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare a fresh measurement against a recorded baseline.

    Returns a verdict dict; ``within_band`` is False when the
    digest differs (nondeterminism — always a failure) or when
    ops/sec drifted beyond ``MAX_BASELINE_DRIFT`` (regression or
    environment change — needs human review, not an automatic
    failure of the code).
    """
    digest_match = (measurement["digest"] == baseline["digest"])
    base_rate = baseline["ops_per_sec"]
    drift = abs(measurement["ops_per_sec"] - base_rate) / base_rate \
        if base_rate > 0 else float("inf")
    return {
        "digest_match": digest_match,
        "baseline_ops_per_sec": base_rate,
        "measured_ops_per_sec": measurement["ops_per_sec"],
        "relative_drift": drift,
        "max_allowed_drift": MAX_BASELINE_DRIFT,
        "within_band": digest_match and drift <= MAX_BASELINE_DRIFT,
    }
