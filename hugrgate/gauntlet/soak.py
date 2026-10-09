"""Long-duration soak with memory-growth detection (slice 488).

``hugrgate/chaos/soak.py`` drives workloads under faults and checks
invariants — but none of its invariants watched memory, so a slow
leak could soak for hours undetected. This module adds the missing
invariant:

- :func:`rss_mb`: current-process RSS in MiB (``resource.getrusage``,
  guarded for non-Unix; None when unobservable).
- :class:`MemoryGrowthInvariant`: a zero-arg callable for
  ``SoakRunner`` invariants — snapshots RSS on first call, raises
  ``AssertionError`` when growth since the snapshot exceeds
  ``budget_mb``. The snapshot refreshes after ``window_ops``
  checks so a slow sawtooth (grow then settle) does not false-positive.
- :func:`run_gate_soak`: the 1.0 soak — drives ``HugrGate.decide``
  end to end under ``SoakRunner`` with the memory invariant armed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MemoryGrowthInvariant",
    "SoakSummary",
    "rss_mb",
    "run_gate_soak",
]


def rss_mb() -> float | None:
    """Current-process RSS in MiB; None when unobservable."""
    try:
        import resource

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes. Heuristic: values
        # below 10**9 cannot be bytes for a live process.
        return (rss_kb / 1024.0) if rss_kb < 10**9 else rss_kb / (1024.0**2)
    except (ImportError, OSError):
        return None


class MemoryGrowthInvariant:
    """Fail when RSS grows more than ``budget_mb`` since the snapshot.

    The snapshot refreshes every ``window_ops`` checks: memory that
    grows and then settles (caches warming up) must not trip the
    invariant forever — only *unbounded* growth within a window
    fails the soak.
    """

    def __init__(self, budget_mb: float = 50.0, window_ops: int = 4) -> None:
        if budget_mb <= 0:
            raise ValueError("budget_mb must be positive")
        if window_ops < 1:
            raise ValueError("window_ops must be >= 1")
        self.budget_mb = budget_mb
        self.window_ops = window_ops
        self._baseline: float | None = None
        self._checks = 0
        self.max_growth_mb = 0.0

    def __call__(self) -> None:
        current = rss_mb()
        if current is None:
            return  # unobservable here; do not fail the soak
        self._checks += 1
        if self._baseline is None:
            self._baseline = current
            return
        growth = current - self._baseline
        self.max_growth_mb = max(self.max_growth_mb, growth)
        if growth > self.budget_mb:
            raise AssertionError(
                f"RSS grew {growth:.1f} MiB since snapshot "
                f"(budget {self.budget_mb:.1f} MiB)"
            )
        if self._checks % self.window_ops == 0:
            self._baseline = current


@dataclass
class SoakSummary:
    """Outcome of :func:`run_gate_soak`."""

    ops: int
    violations: tuple[str, ...]
    errors: dict[str, int]
    max_rss_growth_mb: float
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return not self.violations and not self.errors


def run_gate_soak(*, iterations: int = 500, rss_budget_mb: float = 50.0,
                  duration_s: float = 30.0) -> SoakSummary:
    """Soak the real decision gate and watch for leaks.

    Runs ``iterations`` ``HugrGate.decide`` calls (bounded by
    ``duration_s``) with a deterministic stub backend under
    ``SoakRunner``, armed with the memory-growth invariant.
    """
    from hugrgate.backend import Backend
    from hugrgate.chaos.soak import SoakConfig, SoakRunner
    from hugrgate.core import HugrGate
    from hugrgate.policy import DecisionPolicy
    from hugrgate.result import DecisionResult
    from hugrgate.spec import DecisionSpec

    class _Stub(Backend):
        name = "soak-stub"

        def capabilities(self) -> dict[str, Any]:
            return {"spec_types": ["categorical"]}

        def supports(self, spec: DecisionSpec) -> bool:
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None) -> DecisionResult:
            return DecisionResult(value="a", probability=0.9,
                                  distribution={"a": 0.9, "b": 0.1})

    gate = HugrGate()
    gate.register(_Stub())
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy()
    mem = MemoryGrowthInvariant(budget_mb=rss_budget_mb)

    def _workload(op: int) -> None:
        result = gate.decide({"op": op % 32}, spec, policy)
        assert result.value in ("a", "b")

    runner = SoakRunner(_workload, invariants=[mem])
    started = time.monotonic()
    report = runner.run(SoakConfig(duration_s=duration_s,
                                   target_ops_per_s=1000.0,
                                   max_ops=iterations,
                                   invariant_every_n_ops=25))
    gate.close()
    return SoakSummary(
        ops=report.ops_completed,
        violations=tuple(report.violations),
        errors=dict(report.unexpected_errors),
        max_rss_growth_mb=mem.max_growth_mb,
        elapsed_s=time.monotonic() - started,
    )
