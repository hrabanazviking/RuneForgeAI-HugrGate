"""SLO evaluator. Slice 345.

Evaluates an :class:`SLODefinition
<hugrgate.observability.slo.SLODefinition>` over a window of samples:

- ``evaluate_availability(slo, outcomes)`` — *outcomes* is a list of
  ``(timestamp, ok)`` pairs; only samples inside the window count;
- ``evaluate_latency(slo, latencies_ms)`` — *latencies_ms* is a list of
  ``(timestamp, latency_ms)`` pairs; "good" means within the SLO's
  ``latency_budget_ms``.

Both return an :class:`SLOStatus` with the observed good-fraction, the
burn rate (``observed_bad_rate / error_budget``), the remaining error
budget as a fraction, and a status:

- ``"ok"`` — burn rate ≤ 1 (budget remaining > 0);
- ``"warning"`` — 1 < burn rate ≤ 2 (budget spent faster than allowed);
- ``"breaching"`` — burn rate > 2 (budget exhausting fast).

An empty sample set raises :class:`~hugrgate.errors.SLOError`: an SLO
judged on zero evidence is a configuration bug, not a passing grade.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SLOError
from hugrgate.observability.slo import SLODefinition

__all__ = [
    "STATUSES",
    "SLOEvaluator",
    "SLOStatus",
]

#: Possible evaluation statuses, ordered by severity.
STATUSES = ("ok", "warning", "breaching")


@dataclass(frozen=True)
class SLOStatus:
    """The outcome of evaluating one SLO over one window."""

    slo_name: str
    target: float
    window_s: float
    n_samples: int
    good_fraction: float
    burn_rate: float
    error_budget_remaining: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo_name": self.slo_name,
            "target": self.target,
            "window_s": self.window_s,
            "n_samples": self.n_samples,
            "good_fraction": round(self.good_fraction, 6),
            "burn_rate": round(self.burn_rate, 4),
            "error_budget_remaining": round(self.error_budget_remaining, 4),
            "status": self.status,
        }


class SLOEvaluator:
    """Evaluate SLO definitions over timestamped sample windows."""

    def __init__(self, now: float | None = None) -> None:
        # ``now`` is injectable so tests are deterministic; production
        # uses wall-clock time.
        self._now = now

    def _now_s(self) -> float:
        return self._now if self._now is not None else time.time()

    def _windowed(self, samples: list[tuple[float, Any]],
                  window_s: float) -> list[tuple[float, Any]]:
        now = self._now_s()
        return [(ts, value) for ts, value in samples
                if 0 <= now - ts <= window_s]

    def _verdict(self, slo: SLODefinition, n: int,
                 good: int) -> SLOStatus:
        if n == 0:
            raise SLOError(
                f"SLO {slo.name!r}: no samples inside the "
                f"{slo.window_s}s window — refusing to judge on zero "
                f"evidence")
        bad = n - good
        good_fraction = good / n
        bad_rate = bad / n
        budget = slo.error_budget
        burn_rate = bad_rate / budget if budget > 0 else float("inf")
        # Remaining budget as a fraction of the burn-rate-1 pace:
        # remaining > 0 implies burn_rate <= 1 (status ok).
        remaining = max(0.0, 1.0 - burn_rate)
        if burn_rate > 2.0:
            status = "breaching"
        elif burn_rate > 1.0:
            status = "warning"
        else:
            status = "ok"
        return SLOStatus(
            slo_name=slo.name,
            target=slo.target,
            window_s=slo.window_s,
            n_samples=n,
            good_fraction=good_fraction,
            burn_rate=burn_rate,
            error_budget_remaining=remaining,
            status=status,
        )

    def evaluate_availability(
            self, slo: SLODefinition,
            outcomes: list[tuple[float, bool]]) -> SLOStatus:
        """Evaluate an availability SLO over ``(timestamp, ok)`` samples."""
        windowed = self._windowed(outcomes, slo.window_s)
        good = sum(1 for _, ok in windowed if ok)
        return self._verdict(slo, len(windowed), good)

    def evaluate_latency(
            self, slo: SLODefinition,
            latencies_ms: list[tuple[float, float]]) -> SLOStatus:
        """Evaluate a latency SLO over ``(timestamp, latency_ms)`` samples."""
        if slo.kind != "latency":
            raise SLOError(
                f"evaluate_latency needs a latency SLO, got {slo.kind!r}")
        budget = float(slo.params["latency_budget_ms"])
        windowed = self._windowed(latencies_ms, slo.window_s)
        good = sum(1 for _, ms in windowed if ms <= budget)
        return self._verdict(slo, len(windowed), good)
